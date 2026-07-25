package main

import (
	"context"
	"fmt"
	"io/ioutil"
	"os"
	"strings"

	"github.com/spf13/cobra"
	"github.com/zhfreal/cloudflare-ddns/pkg/cfclient"
	"github.com/zhfreal/cloudflare-ddns/pkg/config"
	"github.com/zhfreal/cloudflare-ddns/pkg/ddns"
	"github.com/zhfreal/cloudflare-ddns/pkg/domain"
	"github.com/zhfreal/cloudflare-ddns/pkg/ipfinder"
)

var recordsCmd = &cobra.Command{
	Use:   "records",
	Short: "Manage DNS records in Cloudflare",
}

// buildDesiredRecords constructs the DesiredRecords map based on domains/zones/raw input
func buildDesiredRecords(ctx context.Context, client *cfclient.Client) (cfclient.DesiredRecords, error) {
	desired := make(cfclient.DesiredRecords)

	initPath := func(zone, prefix string) {
		if desired[zone] == nil {
			desired[zone] = make(map[string]map[cfclient.RecordType]map[string]cfclient.RecordOpts)
		}
		if desired[zone][prefix] == nil {
			desired[zone][prefix] = make(map[cfclient.RecordType]map[string]cfclient.RecordOpts)
		}
	}

	insertRecord := func(zone, prefix string, rType cfclient.RecordType, content string, ttl int, proxied bool) {
		initPath(zone, prefix)
		if desired[zone][prefix][rType] == nil {
			desired[zone][prefix][rType] = make(map[string]cfclient.RecordOpts)
		}
		desired[zone][prefix][rType][content] = cfclient.RecordOpts{
			TTL:     ttl,
			Proxied: proxied,
		}
	}

	// 1. Process standard domains
	if len(Cfg.Domains) > 0 {
		splitDomains := config.SplitContentList(Cfg.Domains, "")
		for _, dom := range splitDomains {
			prefix, zone := domain.SplitDomain(dom, getZoneKeys(client))
			if zone == "" {
				return nil, fmt.Errorf("%s does not have root zone! Please add root zone in CloudFlare.", dom)
			}
			initPath(zone, prefix)
		}
	}

	// 2. Process zone and alias combinations
	if len(Cfg.Zones) > 0 {
		splitZones := config.SplitContentList(Cfg.Zones, "")
		splitAliases := config.SplitContentList(Cfg.Aliases, "")
		if len(splitAliases) == 0 {
			splitAliases = []string{""}
		}

		for _, zone := range splitZones {
			zoneLower := strings.ToLower(zone)
			if _, ok := client.Zones[zoneLower]; !ok {
				return nil, fmt.Errorf("%s is not zone! Please provide valid zone which registered in CloudFlare.", zone)
			}
			for _, alias := range splitAliases {
				initPath(zoneLower, alias)
			}
		}
	}

	// 3. Process IPv4 addrs
	if len(Cfg.IPv4Addrs) > 0 {
		ips := config.SplitContentList(Cfg.IPv4Addrs, "")
		if len(ips) == 1 && ips[0] == "fetch" {
			finder := ipfinder.NewIPFinder(nil)
			resolved, err := finder.FindPublicIP(ctx, 4)
			if err != nil {
				return nil, err
			}
			ips = []string{resolved}
		}

		for zone := range desired {
			for prefix := range desired[zone] {
				for _, ip := range ips {
					insertRecord(zone, prefix, cfclient.RecordTypeA, ip, Cfg.TTL, Cfg.Proxied)
				}
			}
		}
	}

	// 4. Process IPv6 addrs
	if len(Cfg.IPv6Addrs) > 0 {
		ips := config.SplitContentList(Cfg.IPv6Addrs, "")
		if len(ips) == 1 && ips[0] == "fetch" {
			finder := ipfinder.NewIPFinder(nil)
			resolved, err := finder.FindPublicIP(ctx, 6)
			if err != nil {
				return nil, err
			}
			ips = []string{resolved}
		}

		for zone := range desired {
			for prefix := range desired[zone] {
				for _, ip := range ips {
					insertRecord(zone, prefix, cfclient.RecordTypeAAAA, ip, Cfg.TTL, Cfg.Proxied)
				}
			}
		}
	}

	// 5. Process CNAME / CNAME alias
	if Cfg.CNAME != "" || Cfg.CNAMEAlias != "" {
		for zone := range desired {
			for prefix := range desired[zone] {
				content := Cfg.CNAME
				if content == "" {
					if Cfg.CNAMEAlias != "" {
						content = Cfg.CNAMEAlias + "." + zone
					} else {
						content = zone
					}
				}
				insertRecord(zone, prefix, cfclient.RecordTypeCNAME, content, Cfg.TTL, Cfg.Proxied)
			}
		}
	}

	// 6. Process TXT records
	if len(Cfg.TXTRecords) > 0 {
		txts := config.SplitContentList(Cfg.TXTRecords, "TXT")
		for zone := range desired {
			for prefix := range desired[zone] {
				for _, txt := range txts {
					insertRecord(zone, prefix, cfclient.RecordTypeTXT, txt, Cfg.TTL, Cfg.Proxied)
				}
			}
		}
	}

	// 7. Process Raw inputs
	var rawLines []string
	if len(Cfg.Raws) > 0 {
		rawLines = append(rawLines, Cfg.Raws...)
	}
	if Cfg.RawFile != "" {
		content, err := ioutil.ReadFile(Cfg.RawFile)
		if err != nil {
			return nil, fmt.Errorf("failed to read --raw-file %s: %w", Cfg.RawFile, err)
		}
		for _, line := range strings.Split(string(content), "\n") {
			trimmed := strings.TrimSpace(line)
			if trimmed != "" {
				rawLines = append(rawLines, trimmed)
			}
		}
	}

	for _, raw := range rawLines {
		parts, err := config.ParseRawLine(raw)
		if err != nil || len(parts) != 5 {
			return nil, fmt.Errorf("invalid raw content %s", raw)
		}
		prefix := parts[0]
		rType := cfclient.RecordType(strings.ToUpper(parts[1]))
		content := parts[2]
		ttl, err := config.ParseTTL(parts[3])
		if err != nil {
			return nil, fmt.Errorf("invalid ttl %s in raw content %s", parts[3], raw)
		}
		proxied := false
		var sb config.Str2Bool
		if sb.Set(parts[4]) == nil && sb.Value != nil {
			proxied = *sb.Value
		}

		for zone := range desired {
			insertRecord(zone, prefix, rType, content, ttl, proxied)
		}
	}

	// 8. Process Raw Aliases
	var rawAliasLines []string
	if len(Cfg.RawAliases) > 0 {
		rawAliasLines = append(rawAliasLines, Cfg.RawAliases...)
	}
	if Cfg.RawAliasFile != "" {
		content, err := ioutil.ReadFile(Cfg.RawAliasFile)
		if err != nil {
			return nil, fmt.Errorf("failed to read --raw-alias-file %s: %w", Cfg.RawAliasFile, err)
		}
		for _, line := range strings.Split(string(content), "\n") {
			trimmed := strings.TrimSpace(line)
			if trimmed != "" {
				rawAliasLines = append(rawAliasLines, trimmed)
			}
		}
	}

	for _, raw := range rawAliasLines {
		parts, err := config.ParseRawLine(raw)
		if err != nil || len(parts) != 5 {
			return nil, fmt.Errorf("invalid raw content %s", raw)
		}
		prefix := parts[0]
		rType := cfclient.RecordType(strings.ToUpper(parts[1]))
		contentAlias := parts[2]
		ttl, err := config.ParseTTL(parts[3])
		if err != nil {
			return nil, fmt.Errorf("invalid ttl %s in raw content %s", parts[3], raw)
		}
		proxied := false
		var sb config.Str2Bool
		if sb.Set(parts[4]) == nil && sb.Value != nil {
			proxied = *sb.Value
		}

		for zone := range desired {
			content := contentAlias
			if rType == cfclient.RecordTypeCNAME {
				content = contentAlias + "." + zone
			}
			insertRecord(zone, prefix, rType, content, ttl, proxied)
		}
	}

	return desired, nil
}

func getZoneKeys(client *cfclient.Client) map[string]bool {
	keys := make(map[string]bool)
	for k := range client.Zones {
		keys[k] = true
	}
	return keys
}

// Commands definitions

var recordsListCmd = &cobra.Command{
	Use:     "list",
	Aliases: []string{"list-record", "list-records"},
	Short:   "List DNS records for a zone",
	RunE: func(cmd *cobra.Command, args []string) error {
		Cfg.ListRecord = true

		config.LoadFromFile(&Cfg)
		config.ResolveEnvVars(&Cfg)

		if err := config.Validate(&Cfg); err != nil {
			fmt.Fprintln(os.Stderr, err.Error())
			os.Exit(1)
		}

		client, err := cfclient.NewClient(Cfg.Email, Cfg.APIKey, Cfg.APIToken, Cfg.HTTPProxy, Cfg.HTTPSProxy)
		if err != nil {
			return err
		}

		ctx := context.Background()
		err = client.InitZones(ctx)
		if err != nil {
			fmt.Fprintln(os.Stderr, err.Error())
			os.Exit(1)
		}

		desired, err := buildDesiredRecords(ctx, client)
		if err != nil {
			fmt.Fprintln(os.Stderr, err.Error())
			os.Exit(1)
		}

		err = ddns.ListRecords(ctx, client, desired, Cfg.DNSTypes, Cfg.IPv4Addrs, Cfg.IPv6Addrs, Cfg.CNAME, Cfg.CNAMEAlias, Cfg.TXTRecords)
		if err != nil {
			fmt.Fprintln(os.Stderr, err.Error())
			os.Exit(1)
		}

		return nil
	},
}

var recordsAddCmd = &cobra.Command{
	Use:     "add",
	Aliases: []string{"add-record", "add-records"},
	Short:   "Add DNS records to a zone",
	RunE: func(cmd *cobra.Command, args []string) error {
		Cfg.AddRecord = true

		config.LoadFromFile(&Cfg)
		config.ResolveEnvVars(&Cfg)

		if err := config.Validate(&Cfg); err != nil {
			fmt.Fprintln(os.Stderr, err.Error())
			os.Exit(1)
		}

		client, err := cfclient.NewClient(Cfg.Email, Cfg.APIKey, Cfg.APIToken, Cfg.HTTPProxy, Cfg.HTTPSProxy)
		if err != nil {
			return err
		}

		ctx := context.Background()
		err = client.InitZones(ctx)
		if err != nil {
			fmt.Fprintln(os.Stderr, err.Error())
			os.Exit(1)
		}

		desired, err := buildDesiredRecords(ctx, client)
		if err != nil {
			fmt.Fprintln(os.Stderr, err.Error())
			os.Exit(1)
		}

		err = ddns.CreateRecordsNew(ctx, client, desired)
		if err != nil {
			fmt.Fprintln(os.Stderr, err.Error())
			os.Exit(1)
		}

		return nil
	},
}

var recordsUpdateCmd = &cobra.Command{
	Use:     "update",
	Aliases: []string{"update-record", "update-records"},
	Short:   "Update / reconcile DNS records",
	RunE: func(cmd *cobra.Command, args []string) error {
		Cfg.UpdateRecord = true

		config.LoadFromFile(&Cfg)
		config.ResolveEnvVars(&Cfg)

		if err := config.Validate(&Cfg); err != nil {
			fmt.Fprintln(os.Stderr, err.Error())
			os.Exit(1)
		}

		client, err := cfclient.NewClient(Cfg.Email, Cfg.APIKey, Cfg.APIToken, Cfg.HTTPProxy, Cfg.HTTPSProxy)
		if err != nil {
			return err
		}

		ctx := context.Background()
		err = client.InitZones(ctx)
		if err != nil {
			fmt.Fprintln(os.Stderr, err.Error())
			os.Exit(1)
		}

		desired, err := buildDesiredRecords(ctx, client)
		if err != nil {
			fmt.Fprintln(os.Stderr, err.Error())
			os.Exit(1)
		}

		err = ddns.UpdateRecordsNew(ctx, client, desired)
		if err != nil {
			fmt.Fprintln(os.Stderr, err.Error())
			os.Exit(1)
		}

		return nil
	},
}

var recordsDeleteCmd = &cobra.Command{
	Use:     "delete",
	Aliases: []string{"delete-record", "delete-records"},
	Short:   "Delete DNS records from a zone",
	RunE: func(cmd *cobra.Command, args []string) error {
		Cfg.DeleteRecord = true

		config.LoadFromFile(&Cfg)
		config.ResolveEnvVars(&Cfg)

		if err := config.Validate(&Cfg); err != nil {
			fmt.Fprintln(os.Stderr, err.Error())
			os.Exit(1)
		}

		client, err := cfclient.NewClient(Cfg.Email, Cfg.APIKey, Cfg.APIToken, Cfg.HTTPProxy, Cfg.HTTPSProxy)
		if err != nil {
			return err
		}

		ctx := context.Background()
		err = client.InitZones(ctx)
		if err != nil {
			fmt.Fprintln(os.Stderr, err.Error())
			os.Exit(1)
		}

		desired, err := buildDesiredRecords(ctx, client)
		if err != nil {
			fmt.Fprintln(os.Stderr, err.Error())
			os.Exit(1)
		}

		err = ddns.DeleteRecordsNew(ctx, client, desired, Cfg.DNSTypes, Cfg.IPv4Addrs, Cfg.IPv6Addrs, Cfg.CNAME, Cfg.CNAMEAlias, Cfg.TXTRecords)
		if err != nil {
			fmt.Fprintln(os.Stderr, err.Error())
			os.Exit(1)
		}

		return nil
	},
}

func init() {
	recordsCmd.AddCommand(recordsListCmd)
	recordsCmd.AddCommand(recordsAddCmd)
	recordsCmd.AddCommand(recordsUpdateCmd)
	recordsCmd.AddCommand(recordsDeleteCmd)
	rootCmd.AddCommand(recordsCmd)
}
