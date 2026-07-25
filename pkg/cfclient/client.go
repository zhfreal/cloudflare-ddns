package cfclient

import (
	"context"
	"fmt"
	"net/http"
	"net/url"
	"time"

	"github.com/cloudflare/cloudflare-go/v7"
	"github.com/cloudflare/cloudflare-go/v7/dns"
	"github.com/cloudflare/cloudflare-go/v7/option"
	"github.com/cloudflare/cloudflare-go/v7/zones"
)

type RecordType string

const (
	RecordTypeA     RecordType = "A"
	RecordTypeAAAA  RecordType = "AAAA"
	RecordTypeCNAME RecordType = "CNAME"
	RecordTypeTXT   RecordType = "TXT"
)

type RecordOpts struct {
	TTL     int
	Proxied bool
}

// DesiredRecords maps: [zone][prefix][type][content] -> options
type DesiredRecords map[string]map[string]map[RecordType]map[string]RecordOpts

// CloudflareAPI defines the interfaces required from Cloudflare
type CloudflareAPI interface {
	ListZones(ctx context.Context) ([]zones.Zone, error)
	ListDNSRecords(ctx context.Context, zoneID string, domainFilter string) ([]dns.RecordResponse, error)
	CreateDNSRecord(ctx context.Context, params dns.RecordNewParams) (*dns.RecordResponse, error)
	UpdateDNSRecord(ctx context.Context, recordID string, params dns.RecordUpdateParams) (*dns.RecordResponse, error)
	DeleteDNSRecord(ctx context.Context, recordID string, params dns.RecordDeleteParams) (*dns.RecordDeleteResponse, error)
}

// Client implements caching and uses a CloudflareAPI backend
type Client struct {
	apiClient CloudflareAPI
	Email     string
	APIKey    string
	APIToken  string

	// Local Cache
	Zones      map[string]*ZoneMeta
	DNSRecords map[string]*dns.RecordResponse
}

type sdkAPIWrapper struct {
	client *cloudflare.Client
}

func (w *sdkAPIWrapper) ListZones(ctx context.Context) ([]zones.Zone, error) {
	var result []zones.Zone
	iter := w.client.Zones.ListAutoPaging(ctx, zones.ZoneListParams{})
	for iter.Next() {
		result = append(result, iter.Current())
	}
	return result, iter.Err()
}

func (w *sdkAPIWrapper) ListDNSRecords(ctx context.Context, zoneID string, domainFilter string) ([]dns.RecordResponse, error) {
	var result []dns.RecordResponse
	params := dns.RecordListParams{
		ZoneID: cloudflare.F(zoneID),
	}
	if domainFilter != "" {
		params.Name = cloudflare.F(dns.RecordListParamsName{
			Exact: cloudflare.F(domainFilter),
		})
	}
	iter := w.client.DNS.Records.ListAutoPaging(ctx, params)
	for iter.Next() {
		result = append(result, iter.Current())
	}
	return result, iter.Err()
}

func (w *sdkAPIWrapper) CreateDNSRecord(ctx context.Context, params dns.RecordNewParams) (*dns.RecordResponse, error) {
	return w.client.DNS.Records.New(ctx, params)
}

func (w *sdkAPIWrapper) UpdateDNSRecord(ctx context.Context, recordID string, params dns.RecordUpdateParams) (*dns.RecordResponse, error) {
	return w.client.DNS.Records.Update(ctx, recordID, params)
}

func (w *sdkAPIWrapper) DeleteDNSRecord(ctx context.Context, recordID string, params dns.RecordDeleteParams) (*dns.RecordDeleteResponse, error) {
	return w.client.DNS.Records.Delete(ctx, recordID, params)
}

// ZoneMeta stores cached ID and record mappings for a zone
type ZoneMeta struct {
	ID      string
	Records map[string]map[string]map[string]string // [domain][type][content] -> recordID
}

// NewClient initializes the client with Token or Email+Key and proxy options
func NewClient(email, apiKey, apiToken, httpProxy, httpsProxy string) (*Client, error) {
	var opts []option.RequestOption

	transport := http.DefaultTransport.(*http.Transport).Clone()
	if httpProxy != "" || httpsProxy != "" {
		transport.Proxy = func(req *http.Request) (*url.URL, error) {
			if req.URL.Scheme == "https" && httpsProxy != "" {
				return url.Parse(httpsProxy)
			}
			if req.URL.Scheme == "http" && httpProxy != "" {
				return url.Parse(httpProxy)
			}
			return http.ProxyFromEnvironment(req)
		}
	}

	httpClient := &http.Client{
		Timeout:   30 * time.Second,
		Transport: transport,
	}
	opts = append(opts, option.WithHTTPClient(httpClient))

	if apiToken != "" {
		opts = append(opts, option.WithAPIToken(apiToken))
	} else if email != "" && apiKey != "" {
		opts = append(opts, option.WithAPIKey(apiKey), option.WithAPIEmail(email))
	}

	sdkClient := cloudflare.NewClient(opts...)

	return &Client{
		apiClient:  &sdkAPIWrapper{client: sdkClient},
		Email:      email,
		APIKey:     apiKey,
		APIToken:   apiToken,
		Zones:      make(map[string]*ZoneMeta),
		DNSRecords: make(map[string]*dns.RecordResponse),
	}, nil
}

// SetAPIClient overrides the apiClient backend for mocking in tests
func (c *Client) SetAPIClient(api CloudflareAPI) {
	c.apiClient = api
}

// InitZones fetches and caches all zones
func (c *Client) InitZones(ctx context.Context) error {
	zonesList, err := c.apiClient.ListZones(ctx)
	if err != nil {
		return err
	}
	for _, z := range zonesList {
		c.Zones[z.Name] = &ZoneMeta{
			ID:      z.ID,
			Records: make(map[string]map[string]map[string]string),
		}
	}
	if len(c.Zones) == 0 {
		return fmt.Errorf("Can't list zones for you. Please check with Cloudflare!")
	}
	return nil
}

// InitRecordsForZone fetches and caches all DNS records for a given zone
func (c *Client) InitRecordsForZone(ctx context.Context, zoneName string, domainFilter string) error {
	zMeta, exists := c.Zones[zoneName]
	if !exists {
		return fmt.Errorf("Can't find zone %s for you. Please check with Cloudflare!", zoneName)
	}

	recordsList, err := c.apiClient.ListDNSRecords(ctx, zMeta.ID, domainFilter)
	if err != nil {
		return err
	}

	for _, rec := range recordsList {
		if zMeta.Records[rec.Name] == nil {
			zMeta.Records[rec.Name] = make(map[string]map[string]string)
		}
		if zMeta.Records[rec.Name][string(rec.Type)] == nil {
			zMeta.Records[rec.Name][string(rec.Type)] = make(map[string]string)
		}
		zMeta.Records[rec.Name][string(rec.Type)][rec.Content] = rec.ID
		// Take address of local loop variable
		localRec := rec
		c.DNSRecords[rec.ID] = &localRec
	}
	return nil
}

// CreateDNSRecord delegates creation
func (c *Client) CreateDNSRecord(ctx context.Context, params dns.RecordNewParams) (*dns.RecordResponse, error) {
	return c.apiClient.CreateDNSRecord(ctx, params)
}

// UpdateDNSRecord delegates update
func (c *Client) UpdateDNSRecord(ctx context.Context, recordID string, params dns.RecordUpdateParams) (*dns.RecordResponse, error) {
	return c.apiClient.UpdateDNSRecord(ctx, recordID, params)
}

// DeleteDNSRecord delegates deletion
func (c *Client) DeleteDNSRecord(ctx context.Context, recordID string, params dns.RecordDeleteParams) (*dns.RecordDeleteResponse, error) {
	return c.apiClient.DeleteDNSRecord(ctx, recordID, params)
}
