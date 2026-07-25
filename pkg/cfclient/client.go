package cfclient

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
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

type Zone struct {
	ID   string `json:"id"`
	Name string `json:"name"`
}

type DNSRecord struct {
	ID      string `json:"id,omitempty"`
	Type    string `json:"type"`
	Name    string `json:"name"`
	Content string `json:"content"`
	TTL     int    `json:"ttl"`
	Proxied bool   `json:"proxied"`
}

type DNSRecordDeleteResponse struct {
	ID string `json:"id"`
}

type ResponseError struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
}

type resultInfo struct {
	Page       int `json:"page"`
	PerPage    int `json:"per_page"`
	TotalPages int `json:"total_pages"`
	Count      int `json:"count"`
	TotalCount int `json:"total_count"`
}

type zoneListResponse struct {
	Result     []Zone          `json:"result"`
	ResultInfo resultInfo      `json:"result_info"`
	Success    bool            `json:"success"`
	Errors     []ResponseError `json:"errors"`
}

type recordListResponse struct {
	Result     []DNSRecord     `json:"result"`
	ResultInfo resultInfo      `json:"result_info"`
	Success    bool            `json:"success"`
	Errors     []ResponseError `json:"errors"`
}

type recordSingleResponse struct {
	Result     DNSRecord       `json:"result"`
	Success    bool            `json:"success"`
	Errors     []ResponseError `json:"errors"`
}

type recordDeleteResponse struct {
	Result     DNSRecordDeleteResponse `json:"result"`
	Success    bool                    `json:"success"`
	Errors     []ResponseError         `json:"errors"`
}

// CloudflareAPI defines the interfaces required from Cloudflare
type CloudflareAPI interface {
	ListZones(ctx context.Context) ([]Zone, error)
	ListDNSRecords(ctx context.Context, zoneID string, domainFilter string) ([]DNSRecord, error)
	CreateDNSRecord(ctx context.Context, zoneID string, record DNSRecord) (*DNSRecord, error)
	UpdateDNSRecord(ctx context.Context, zoneID string, recordID string, record DNSRecord) (*DNSRecord, error)
	DeleteDNSRecord(ctx context.Context, zoneID string, recordID string) (*DNSRecordDeleteResponse, error)
}

// Client implements caching and uses a CloudflareAPI backend
type Client struct {
	apiClient CloudflareAPI
	Email     string
	APIKey    string
	APIToken  string

	httpClient *http.Client

	// Local Cache
	Zones      map[string]*ZoneMeta
	DNSRecords map[string]*DNSRecord
}

type apiWrapper struct {
	client *Client
}

func parseErrors(errors []ResponseError) error {
	var errMsgs []string
	for _, e := range errors {
		errMsgs = append(errMsgs, fmt.Sprintf("[%d] %s", e.Code, e.Message))
	}
	return fmt.Errorf("cloudflare API error: %s", strings.Join(errMsgs, ", "))
}

func (w *apiWrapper) ListZones(ctx context.Context) ([]Zone, error) {
	var allZones []Zone
	page := 1
	for {
		var resp zoneListResponse
		path := fmt.Sprintf("/zones?per_page=50&page=%d", page)
		err := w.client.doRequest(ctx, "GET", path, nil, &resp)
		if err != nil {
			return nil, err
		}
		if !resp.Success || len(resp.Errors) > 0 {
			return nil, parseErrors(resp.Errors)
		}
		allZones = append(allZones, resp.Result...)
		if len(allZones) >= resp.ResultInfo.TotalCount || len(resp.Result) == 0 {
			break
		}
		page++
	}
	return allZones, nil
}

func (w *apiWrapper) ListDNSRecords(ctx context.Context, zoneID string, domainFilter string) ([]DNSRecord, error) {
	var allRecords []DNSRecord
	page := 1
	for {
		var resp recordListResponse
		path := fmt.Sprintf("/zones/%s/dns_records?per_page=100&page=%d", zoneID, page)
		if domainFilter != "" {
			path += "&name=" + url.QueryEscape(domainFilter)
		}
		err := w.client.doRequest(ctx, "GET", path, nil, &resp)
		if err != nil {
			return nil, err
		}
		if !resp.Success || len(resp.Errors) > 0 {
			return nil, parseErrors(resp.Errors)
		}
		allRecords = append(allRecords, resp.Result...)
		if len(allRecords) >= resp.ResultInfo.TotalCount || len(resp.Result) == 0 {
			break
		}
		page++
	}
	return allRecords, nil
}

func (w *apiWrapper) CreateDNSRecord(ctx context.Context, zoneID string, record DNSRecord) (*DNSRecord, error) {
	var resp recordSingleResponse
	path := fmt.Sprintf("/zones/%s/dns_records", zoneID)
	err := w.client.doRequest(ctx, "POST", path, record, &resp)
	if err != nil {
		return nil, err
	}
	if !resp.Success || len(resp.Errors) > 0 {
		return nil, parseErrors(resp.Errors)
	}
	return &resp.Result, nil
}

func (w *apiWrapper) UpdateDNSRecord(ctx context.Context, zoneID string, recordID string, record DNSRecord) (*DNSRecord, error) {
	var resp recordSingleResponse
	path := fmt.Sprintf("/zones/%s/dns_records/%s", zoneID, recordID)
	err := w.client.doRequest(ctx, "PATCH", path, record, &resp)
	if err != nil {
		return nil, err
	}
	if !resp.Success || len(resp.Errors) > 0 {
		return nil, parseErrors(resp.Errors)
	}
	return &resp.Result, nil
}

func (w *apiWrapper) DeleteDNSRecord(ctx context.Context, zoneID string, recordID string) (*DNSRecordDeleteResponse, error) {
	var resp recordDeleteResponse
	path := fmt.Sprintf("/zones/%s/dns_records/%s", zoneID, recordID)
	err := w.client.doRequest(ctx, "DELETE", path, nil, &resp)
	if err != nil {
		return nil, err
	}
	if !resp.Success || len(resp.Errors) > 0 {
		return nil, parseErrors(resp.Errors)
	}
	return &resp.Result, nil
}

// ZoneMeta stores cached ID and record mappings for a zone
type ZoneMeta struct {
	ID      string
	Records map[string]map[string]map[string]string // [domain][type][content] -> recordID
}

// NewClient initializes the client with Token or Email+Key and proxy options
func NewClient(email, apiKey, apiToken, httpProxy, httpsProxy string) (*Client, error) {
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

	c := &Client{
		Email:      email,
		APIKey:     apiKey,
		APIToken:   apiToken,
		httpClient: httpClient,
		Zones:      make(map[string]*ZoneMeta),
		DNSRecords: make(map[string]*DNSRecord),
	}
	c.apiClient = &apiWrapper{client: c}
	return c, nil
}

func (c *Client) doRequest(ctx context.Context, method, path string, body interface{}, responseObj interface{}) error {
	var bodyReader io.Reader
	if body != nil {
		data, err := json.Marshal(body)
		if err != nil {
			return fmt.Errorf("failed to marshal request body: %w", err)
		}
		bodyReader = bytes.NewReader(data)
	}

	req, err := http.NewRequestWithContext(ctx, method, "https://api.cloudflare.com/client/v4"+path, bodyReader)
	if err != nil {
		return fmt.Errorf("failed to create request: %w", err)
	}

	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}

	if c.APIToken != "" {
		req.Header.Set("Authorization", "Bearer "+c.APIToken)
	} else if c.Email != "" && c.APIKey != "" {
		req.Header.Set("X-Auth-Email", c.Email)
		req.Header.Set("X-Auth-Key", c.APIKey)
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("request failed: %w", err)
	}
	defer resp.Body.Close()

	if err := json.NewDecoder(resp.Body).Decode(responseObj); err != nil {
		return fmt.Errorf("failed to decode response (status %d): %w", resp.StatusCode, err)
	}

	return nil
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
		if zMeta.Records[rec.Name][rec.Type] == nil {
			zMeta.Records[rec.Name][rec.Type] = make(map[string]string)
		}
		zMeta.Records[rec.Name][rec.Type][rec.Content] = rec.ID
		localRec := rec
		c.DNSRecords[rec.ID] = &localRec
	}
	return nil
}

// CreateDNSRecord delegates creation
func (c *Client) CreateDNSRecord(ctx context.Context, zoneID string, record DNSRecord) (*DNSRecord, error) {
	return c.apiClient.CreateDNSRecord(ctx, zoneID, record)
}

// UpdateDNSRecord delegates update
func (c *Client) UpdateDNSRecord(ctx context.Context, zoneID string, recordID string, record DNSRecord) (*DNSRecord, error) {
	return c.apiClient.UpdateDNSRecord(ctx, zoneID, recordID, record)
}

// DeleteDNSRecord delegates deletion
func (c *Client) DeleteDNSRecord(ctx context.Context, zoneID string, recordID string) (*DNSRecordDeleteResponse, error) {
	return c.apiClient.DeleteDNSRecord(ctx, zoneID, recordID)
}
