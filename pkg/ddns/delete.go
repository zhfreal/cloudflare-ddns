package ddns

import (
	"context"
	"fmt"
	"strings"
	"time"

	"github.com/zhfreal/cloudflare-ddns/pkg/cfclient"
)

// DeleteRecordsNew implements Python's delete_records_new
func DeleteRecordsNew(
	ctx context.Context,
	client *cfclient.Client,
	recordsDict cfclient.DesiredRecords,
	dnsTypes []string,
	ipv4Addrs []string,
	ipv6Addrs []string,
	cname string,
	cnameAlias string,
	txtRecords []string,
	ids []string,
) error {
	hasContentFilters := len(ipv4Addrs) > 0 || len(ipv6Addrs) > 0 || cname != "" || cnameAlias != "" || len(txtRecords) > 0

	// Helper to check if a slice contains a string case-insensitively
	containsIgnoreCase := func(slice []string, val string) bool {
		valUpper := strings.ToUpper(val)
		for _, s := range slice {
			if strings.ToUpper(s) == valUpper {
				return true
			}
		}
		return false
	}

	for tZone, prefixMap := range recordsDict {
		tZone = strings.ToLower(tZone)
		err := client.InitRecordsForZone(ctx, tZone, "")
		if err != nil {
			return err
		}

		zoneID := client.Zones[tZone].ID

		var prefixes []string
		if len(prefixMap) > 0 {
			for pref := range prefixMap {
				prefixes = append(prefixes, pref)
			}
		}

		var subDomains []string
		if len(prefixes) > 0 {
			for _, pref := range prefixes {
				if pref == "" {
					subDomains = append(subDomains, tZone)
				} else {
					subDomains = append(subDomains, pref+"."+tZone)
				}
			}
		} else {
			zRecords := client.Zones[tZone].Records
			for sub := range zRecords {
				subDomains = append(subDomains, sub)
			}
		}

		type recordDelItem struct {
			subDomain string
			dnsType   string
			content   string
			recordID  string
		}

		var recordIDListForDel []recordDelItem

		for _, tSubDomain := range subDomains {
			zRecords := client.Zones[tZone].Records
			subMap, exists := zRecords[tSubDomain]
			if !exists {
				continue
			}

			tPrefix := ""
			if tSubDomain != tZone {
				tPrefix = strings.TrimSuffix(tSubDomain, "."+tZone)
				tPrefix = strings.Trim(tPrefix, ".")
			}

			var prefixTypes []string
			if len(prefixes) > 0 && prefixMap[tPrefix] != nil {
				for dt := range prefixMap[tPrefix] {
					prefixTypes = append(prefixTypes, string(dt))
				}
			} else if len(dnsTypes) > 0 {
				prefixTypes = dnsTypes
			}

			if len(prefixTypes) > 0 {
				for _, dnsType := range prefixTypes {
					dnsType = strings.ToUpper(dnsType)
					if typeMap, ok := subMap[dnsType]; ok {
						for content, recordID := range typeMap {
							matched := false
							if hasContentFilters {
								switch dnsType {
								case "A":
									if len(ipv4Addrs) > 0 && containsIgnoreCase(ipv4Addrs, content) {
										matched = true
									}
								case "AAAA":
									if len(ipv6Addrs) > 0 && containsIgnoreCase(ipv6Addrs, content) {
										matched = true
									}
								case "CNAME":
									if cname != "" && strings.EqualFold(content, cname) {
										matched = true
									} else if cnameAlias != "" {
										aliasWithZone := cnameAlias + "." + tZone
										if strings.EqualFold(content, cnameAlias) || strings.EqualFold(content, aliasWithZone) {
											matched = true
										}
									}
								case "TXT":
									if len(txtRecords) > 0 && containsIgnoreCase(txtRecords, content) {
										matched = true
									}
								default:
									if cname != "" && strings.Contains(strings.ToLower(content), strings.ToLower(cname)) {
										matched = true
									} else if len(txtRecords) > 0 && containsIgnoreCase(txtRecords, content) {
										matched = true
									} else if len(ipv4Addrs) > 0 && containsIgnoreCase(ipv4Addrs, content) {
										matched = true
									} else if len(ipv6Addrs) > 0 && containsIgnoreCase(ipv6Addrs, content) {
										matched = true
									}
								}
							} else {
								matched = true
							}

							if matched {
								if len(ids) > 0 && !containsIgnoreCase(ids, recordID) {
									matched = false
								}
							}

							if matched {
								recordIDListForDel = append(recordIDListForDel, recordDelItem{
									subDomain: tSubDomain,
									dnsType:   dnsType,
									content:   content,
									recordID:  recordID,
								})
							}
						}
					}
				}
			} else {
				for dnsType, typeMap := range subMap {
					for content, recordID := range typeMap {
						matched := false
						if hasContentFilters {
							switch dnsType {
							case "A":
								if len(ipv4Addrs) > 0 && containsIgnoreCase(ipv4Addrs, content) {
									matched = true
								}
							case "AAAA":
								if len(ipv6Addrs) > 0 && containsIgnoreCase(ipv6Addrs, content) {
									matched = true
								}
							case "CNAME":
								if cname != "" && strings.EqualFold(content, cname) {
									matched = true
								} else if cnameAlias != "" {
									aliasWithZone := cnameAlias + "." + tZone
									if strings.EqualFold(content, cnameAlias) || strings.EqualFold(content, aliasWithZone) {
										matched = true
									}
								}
							case "TXT":
								if len(txtRecords) > 0 && containsIgnoreCase(txtRecords, content) {
									matched = true
								}
							default:
								if cname != "" && strings.Contains(strings.ToLower(content), strings.ToLower(cname)) {
									matched = true
								} else if len(txtRecords) > 0 && containsIgnoreCase(txtRecords, content) {
									matched = true
								} else if len(ipv4Addrs) > 0 && containsIgnoreCase(ipv4Addrs, content) {
									matched = true
								} else if len(ipv6Addrs) > 0 && containsIgnoreCase(ipv6Addrs, content) {
									matched = true
								}
							}
						} else {
							matched = true
						}

						if matched {
							if len(ids) > 0 && !containsIgnoreCase(ids, recordID) {
								matched = false
							}
						}

						if matched {
							recordIDListForDel = append(recordIDListForDel, recordDelItem{
								subDomain: tSubDomain,
								dnsType:   dnsType,
								content:   content,
								recordID:  recordID,
							})
						}
					}
				}
			}
		}

		for _, item := range recordIDListForDel {
			_, err := client.DeleteDNSRecord(ctx, zoneID, item.recordID)
			if err != nil {
				return fmt.Errorf("Failed to delete record ID %s on %s (%s, %s): %w",
					item.recordID, item.subDomain, item.dnsType, item.content, err)
			}

			// Clean cache
			delete(client.DNSRecords, item.recordID)
			if client.Zones[tZone].Records[item.subDomain] != nil && client.Zones[tZone].Records[item.subDomain][item.dnsType] != nil {
				delete(client.Zones[tZone].Records[item.subDomain][item.dnsType], item.content)
			}

			fmt.Printf("Succeed to delete [%s, %s, %s]\n", item.subDomain, item.dnsType, item.content)
			time.Sleep(100 * time.Millisecond)
		}
	}
	return nil
}
