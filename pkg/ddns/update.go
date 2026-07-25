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

// UpdateRecordsNew implements the 4-phase DDNS update reconciliation algorithm
func UpdateRecordsNew(ctx context.Context, client *cfclient.Client, recordsDict cfclient.DesiredRecords) error {
	for tZone, prefixMap := range recordsDict {
		tZone = strings.ToLower(tZone)
		err := client.InitRecordsForZone(ctx, tZone, "")
		if err != nil {
			return err
		}

		zoneID := client.Zones[tZone].ID

		for tPrefix, typeMap := range prefixMap {
			tFullDomain := tZone
			if tPrefix != "" {
				tFullDomain = tPrefix + "." + tZone
			}

			for dnsType, contentMap := range typeMap {
				dnsTypeStr := strings.ToUpper(string(dnsType))

				// Get current records in cache for this domain and type
				tCurrentRecordsDict := make(map[string]string) // content -> ID
				if client.Zones[tZone].Records[tFullDomain] != nil && client.Zones[tZone].Records[tFullDomain][dnsTypeStr] != nil {
					tCurrentRecordsDict = client.Zones[tZone].Records[tFullDomain][dnsTypeStr]
				}

				type recordUpdateItem struct {
					content string
					ttl     int
					proxied bool
				}

				// Phase 1: Classify desired records into exist and non-exist
				var tExistContents []recordUpdateItem
				var tNonExistContents []recordUpdateItem

				for tContent, opts := range contentMap {
					// Check txt type proxied constraint
					proxiedVal := opts.Proxied
					ttlVal := opts.TTL
					if dnsTypeStr == "TXT" {
						proxiedVal = false
					}
					if proxiedVal {
						ttlVal = 1
					}

					if _, exists := tCurrentRecordsDict[tContent]; exists {
						tExistContents = append(tExistContents, recordUpdateItem{
							content: tContent,
							ttl:     ttlVal,
							proxied: proxiedVal,
						})
					} else {
						tNonExistContents = append(tNonExistContents, recordUpdateItem{
							content: tContent,
							ttl:     ttlVal,
							proxied: proxiedVal,
						})
					}
				}

				// Phase 2: Identify extra records currently registered on Cloudflare
				var tExtraRecords []string
				for tContent, tRecordID := range tCurrentRecordsDict {
					tRecord, exists := client.DNSRecords[tRecordID]
					if !exists {
						continue
					}

					tName := tRecord.Name
					tType := tRecord.Type
					tCurrPrefix := ""
					if tName != tZone {
						tCurrPrefix = strings.TrimSuffix(tName, "."+tZone)
						tCurrPrefix = strings.Trim(tCurrPrefix, ".")
					}

					// If the current prefix, type, or content is not in our desired set, it is extra
					if recordsDict[tZone] == nil ||
						recordsDict[tZone][tCurrPrefix] == nil ||
						recordsDict[tZone][tCurrPrefix][cfclient.RecordType(tType)] == nil ||
						recordsDict[tZone][tCurrPrefix][cfclient.RecordType(tType)][tContent] == (cfclient.RecordOpts{}) {
						tExtraRecords = append(tExtraRecords, tContent)
					}
				}

				// Phase 3: Update existing records whose TTL or Proxied changed
				for _, item := range tExistContents {
					tRecordID := tCurrentRecordsDict[item.content]
					cachedRecord := client.DNSRecords[tRecordID]

					// Convert SDK cached values to int TTL and bool Proxied
					cachedTTL := int(cachedRecord.TTL)
					cachedProxied := cachedRecord.Proxied

					if item.ttl != cachedTTL || item.proxied != cachedProxied {
						body := dns.RecordUpdateParamsBody{
							Name:    cloudflare.F(tFullDomain),
							Type:    cloudflare.F(dns.RecordUpdateParamsBodyType(dnsTypeStr)),
							Content: cloudflare.F(item.content),
							TTL:     cloudflare.F(dns.TTL(item.ttl)),
							Proxied: cloudflare.F(item.proxied),
						}
						params := dns.RecordUpdateParams{
							ZoneID: cloudflare.F(zoneID),
							Body:   body,
						}

						updatedRecord, err := client.UpdateDNSRecord(ctx, tRecordID, params)
						if err != nil {
							return fmt.Errorf("Failed to update record ID %s: %w", tRecordID, err)
						}

						// Update cache
						client.DNSRecords[tRecordID] = updatedRecord

						fmt.Printf("Update %s, %s, %s, from [%d, %t] to [%d, %t]\n",
							tFullDomain, dnsTypeStr, item.content, cachedTTL, cachedProxied, item.ttl, item.proxied)
						time.Sleep(100 * time.Millisecond)
					}
				}

				// Phase 4: Re-purpose extra records to fulfill non-existent desired records
				for len(tExtraRecords) > 0 && len(tNonExistContents) > 0 {
					tNewItem := tNonExistContents[0]
					tOldContent := tExtraRecords[0]
					tRecordID := tCurrentRecordsDict[tOldContent]
					cachedRecord := client.DNSRecords[tRecordID]

					cachedTTL := int(cachedRecord.TTL)
					cachedProxied := cachedRecord.Proxied

					body := dns.RecordUpdateParamsBody{
						Name:    cloudflare.F(tFullDomain),
						Type:    cloudflare.F(dns.RecordUpdateParamsBodyType(dnsTypeStr)),
						Content: cloudflare.F(tNewItem.content),
						TTL:     cloudflare.F(dns.TTL(tNewItem.ttl)),
						Proxied: cloudflare.F(tNewItem.proxied),
					}
					params := dns.RecordUpdateParams{
						ZoneID: cloudflare.F(zoneID),
						Body:   body,
					}

					updatedRecord, err := client.UpdateDNSRecord(ctx, tRecordID, params)
					if err != nil {
						return fmt.Errorf("Failed to update extra record ID %s: %w", tRecordID, err)
					}

					// Update cache: remove old cache mapping, insert new
					delete(client.Zones[tZone].Records[tFullDomain][dnsTypeStr], tOldContent)
					client.Zones[tZone].Records[tFullDomain][dnsTypeStr][tNewItem.content] = tRecordID
					client.DNSRecords[tRecordID] = updatedRecord

					fmt.Printf("Update %s, %s, from [%s, %d, %t] to [%s, %d, %t]\n",
						tFullDomain, dnsTypeStr, tOldContent, cachedTTL, cachedProxied, tNewItem.content, tNewItem.ttl, tNewItem.proxied)

					tNonExistContents = tNonExistContents[1:]
					tExtraRecords = tExtraRecords[1:]
					time.Sleep(100 * time.Millisecond)
				}

				// Phase 5: Delete any remaining surplus extra records
				for _, tContent := range tExtraRecords {
					tRecordID := tCurrentRecordsDict[tContent]
					delParams := dns.RecordDeleteParams{
						ZoneID: cloudflare.F(zoneID),
					}

					_, err := client.DeleteDNSRecord(ctx, tRecordID, delParams)
					if err != nil {
						return fmt.Errorf("Failed to delete extra record %s: %w", tContent, err)
					}

					// Clean cache
					delete(client.DNSRecords, tRecordID)
					delete(client.Zones[tZone].Records[tFullDomain][dnsTypeStr], tContent)

					fmt.Printf("Delete [%s, %s, %s]\n", tFullDomain, dnsTypeStr, tContent)
					time.Sleep(100 * time.Millisecond)
				}

				// Phase 6: Create any remaining non-existent desired records
				for _, item := range tNonExistContents {
					body := dns.RecordNewParamsBody{
						Name:    cloudflare.F(tFullDomain),
						Type:    cloudflare.F(dns.RecordNewParamsBodyType(dnsTypeStr)),
						Content: cloudflare.F(item.content),
						TTL:     cloudflare.F(dns.TTL(item.ttl)),
						Proxied: cloudflare.F(item.proxied),
					}
					params := dns.RecordNewParams{
						ZoneID: cloudflare.F(zoneID),
						Body:   body,
					}

					rec, err := client.CreateDNSRecord(ctx, params)
					if err != nil {
						return fmt.Errorf("Failed to create record %s: %w", item.content, err)
					}

					// Cache update
					client.DNSRecords[rec.ID] = rec
					if client.Zones[tZone].Records[rec.Name] == nil {
						client.Zones[tZone].Records[rec.Name] = make(map[string]map[string]string)
					}
					if client.Zones[tZone].Records[rec.Name][string(rec.Type)] == nil {
						client.Zones[tZone].Records[rec.Name][string(rec.Type)] = make(map[string]string)
					}
					client.Zones[tZone].Records[rec.Name][string(rec.Type)][rec.Content] = rec.ID

					fmt.Printf("Create [%s, %s, %s]\n", tFullDomain, dnsTypeStr, item.content)
					time.Sleep(100 * time.Millisecond)
				}
			}
		}
	}
	return nil
}
