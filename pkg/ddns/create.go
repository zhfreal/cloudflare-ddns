package ddns

import (
	"context"
	"fmt"
	"strings"
	"time"

	"github.com/cloudflare/cloudflare-go/v7"
	"github.com/cloudflare/cloudflare-go/v7/dns"
	"github.com/zhfreal/cloudflare-ddns/pkg/cfclient"
)

// CreateRecordsNew implements Python's create_records_new
func CreateRecordsNew(ctx context.Context, client *cfclient.Client, recordsDict cfclient.DesiredRecords) error {
	for tZone, prefixMap := range recordsDict {
		tZone = strings.ToLower(tZone)
		err := client.InitRecordsForZone(ctx, tZone, "")
		if err != nil {
			return err
		}

		zoneID := client.Zones[tZone].ID

		for tPrefix, typeMap := range prefixMap {
			tSubDomain := tZone
			if tPrefix != "" {
				tSubDomain = tPrefix + "." + tZone
			}

			for dnsType, contentMap := range typeMap {
				tCurrentRecords := make(map[string]string)
				if client.Zones[tZone].Records[tSubDomain] != nil && client.Zones[tZone].Records[tSubDomain][string(dnsType)] != nil {
					tCurrentRecords = client.Zones[tZone].Records[tSubDomain][string(dnsType)]
				}

				for tContent, opts := range contentMap {
					if _, exists := tCurrentRecords[tContent]; exists {
						fmt.Printf("Escape existing record (%s, %s, %s)\n", tSubDomain, dnsType, tContent)
					} else {
						// Apply TTL and Proxied overrides
						ttlVal := opts.TTL
						proxiedVal := opts.Proxied
						if dnsType == "TXT" {
							proxiedVal = false
						}
						if proxiedVal {
							ttlVal = 1
						}

						body := dns.RecordNewParamsBody{
							Name:    cloudflare.F(tSubDomain),
							Type:    cloudflare.F(dns.RecordNewParamsBodyType(dnsType)),
							Content: cloudflare.F(tContent),
							TTL:     cloudflare.F(dns.TTL(ttlVal)),
							Proxied: cloudflare.F(proxiedVal),
						}
						params := dns.RecordNewParams{
							ZoneID: cloudflare.F(zoneID),
							Body:   body,
						}

						rec, err := client.CreateDNSRecord(ctx, params)
						if err != nil {
							return fmt.Errorf("Failed to create %q records for zone: %q, %w", tSubDomain, tZone, err)
						}

						// Update local cache
						client.DNSRecords[rec.ID] = rec
						zMeta := client.Zones[tZone]
						if zMeta.Records[rec.Name] == nil {
							zMeta.Records[rec.Name] = make(map[string]map[string]string)
						}
						if zMeta.Records[rec.Name][string(rec.Type)] == nil {
							zMeta.Records[rec.Name][string(rec.Type)] = make(map[string]string)
						}
						zMeta.Records[rec.Name][string(rec.Type)][rec.Content] = rec.ID

						fmt.Printf("Succeed to created a record (%s, %s, %s)\n", tSubDomain, dnsType, tContent)
						time.Sleep(100 * time.Millisecond)
					}
				}
			}
		}
	}
	return nil
}
