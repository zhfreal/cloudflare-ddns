package ddns

import (
	"context"
	"fmt"
	"os"
	"sort"
	"text/tabwriter"

	"github.com/zhfreal/cloudflare-ddns/pkg/cfclient"
)

// ListZones prints all cached zone names
func ListZones(client *cfclient.Client) {
	for name := range client.Zones {
		fmt.Println(name)
	}
}

type recordRow struct {
	Name    string
	Type    string
	Content string
	TTL     int
	Proxied bool
	ID      string
}

// ListRecords prints filtered DNS records in a beautiful formatted table
func ListRecords(
	ctx context.Context,
	client *cfclient.Client,
	records map[string]map[string]map[cfclient.RecordType]map[string]cfclient.RecordOpts,
	dnsTypes []string,
	ipv4Addrs []string,
	ipv6Addrs []string,
	cname string,
	cnameAlias string,
	txtRecords []string,
) error {
	hasContentFilters := len(ipv4Addrs) > 0 || len(ipv6Addrs) > 0 || cname != "" || cnameAlias != "" || len(txtRecords) > 0

	// Helper to check if a slice contains a string
	contains := func(slice []string, val string) bool {
		for _, s := range slice {
			if s == val {
				return true
			}
		}
		return false
	}

	zonesToList := make(map[string]bool)
	if len(records) > 0 {
		for z := range records {
			zonesToList[z] = true
		}
	} else {
		for z := range client.Zones {
			zonesToList[z] = true
		}
	}

	var rows []recordRow

	for tZone := range zonesToList {
		err := client.InitRecordsForZone(ctx, tZone, "")
		if err != nil {
			return err
		}

		var prefixes []string
		if records != nil && records[tZone] != nil {
			for pref := range records[tZone] {
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

		for _, tSubDomain := range subDomains {
			zRecords := client.Zones[tZone].Records
			subMap, exists := zRecords[tSubDomain]
			if !exists {
				continue
			}

			var recordIDList []string
			for rType, valMap := range subMap {
				// Filter by dnsTypes if provided
				if len(dnsTypes) > 0 && !contains(dnsTypes, rType) {
					continue
				}

				for tContent, tID := range valMap {
					if hasContentFilters {
						matched := false
						switch rType {
						case "A":
							if len(ipv4Addrs) > 0 && contains(ipv4Addrs, tContent) {
								matched = true
							}
						case "AAAA":
							if len(ipv6Addrs) > 0 && contains(ipv6Addrs, tContent) {
								matched = true
							}
						case "CNAME":
							if cname != "" && tContent == cname {
								matched = true
							} else if cnameAlias != "" {
								aliasWithZone := cnameAlias + "." + tZone
								if tContent == cnameAlias || tContent == aliasWithZone {
									matched = true
								}
							}
						case "TXT":
							if len(txtRecords) > 0 && contains(txtRecords, tContent) {
								matched = true
							}
						}

						if matched {
							recordIDList = append(recordIDList, tID)
						}
					} else {
						recordIDList = append(recordIDList, tID)
					}
				}
			}

			for _, tID := range recordIDList {
				if rec, exists := client.DNSRecords[tID]; exists {
					rows = append(rows, recordRow{
						Name:    rec.Name,
						Type:    string(rec.Type),
						Content: rec.Content,
						TTL:     int(rec.TTL),
						Proxied: rec.Proxied,
						ID:      rec.ID,
					})
				}
			}
		}
	}

	if len(rows) > 0 {
		sort.Slice(rows, func(i, j int) bool {
			if rows[i].Name != rows[j].Name {
				return rows[i].Name < rows[j].Name
			}
			if rows[i].Type != rows[j].Type {
				return rows[i].Type < rows[j].Type
			}
			return rows[i].Content < rows[j].Content
		})

		w := tabwriter.NewWriter(os.Stdout, 0, 0, 3, ' ', 0)
		fmt.Fprintln(w, "NAME\tTYPE\tCONTENT\tTTL\tPROXIED\tID")
		for _, row := range rows {
			fmt.Fprintf(w, "%s\t%s\t%s\t%d\t%t\t%s\n", row.Name, row.Type, row.Content, row.TTL, row.Proxied, row.ID)
		}
		w.Flush()
	}

	return nil
}
