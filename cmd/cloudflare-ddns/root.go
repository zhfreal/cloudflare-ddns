package main

import (
	"fmt"
	"os"
	"strings"

	"github.com/spf13/cobra"
	"github.com/zhfreal/cloudflare-ddns/pkg/config"
	"github.com/zhfreal/cloudflare-ddns/pkg/version"
)

var (
	// Cfg is the global configuration options parsed from CLI
	Cfg config.Config
)

var rootCmd = &cobra.Command{
	Use:   "cloudflare-ddns",
	Short: "cloudflare-ddns is a DDNS helper for Cloudflare",
	Long: `cloudflare-ddns 26.07.25
  - a DDNS helper for Cloudflare.
  - create, delete or update dns record for dns type "A|AAAA|CNAME|TXT".`,
	RunE: func(cmd *cobra.Command, args []string) error {
		if Cfg.Version {
			fmt.Printf("cloudflare-ddns %s (commit %s)\n", version.Version, version.GitCommit)
			os.Exit(0)
		}
		// If no subcommands matched and no legacy mode was intercepted, show help
		return cmd.Help()
	},
}

func init() {
	// Global / Persistent Flags
	rootCmd.PersistentFlags().StringVarP(&Cfg.Email, "email", "e", "", "Email for your cloudflare account")
	rootCmd.PersistentFlags().StringVarP(&Cfg.APIKey, "api-key", "k", "", "API Key of your cloudflare account")
	rootCmd.PersistentFlags().StringVar(&Cfg.APIToken, "api-token", "", "API Token for Cloudflare with \"Authorization: Bearer\" authentication")
	rootCmd.PersistentFlags().StringSliceVarP(&Cfg.Zones, "zone", "z", nil, "root domain, zone in cloudflare")
	rootCmd.PersistentFlags().StringSliceVarP(&Cfg.Domains, "domain", "d", nil, "subdomain in cloudflare")
	rootCmd.PersistentFlags().StringSliceVarP(&Cfg.Aliases, "alias", "a", nil, "alias of domain")
	rootCmd.PersistentFlags().StringSliceVarP(&Cfg.IPv4Addrs, "ipv4", "4", nil, "IPv4 address for action")
	rootCmd.PersistentFlags().StringSliceVarP(&Cfg.IPv6Addrs, "ipv6", "6", nil, "IPv6 address for action")
	rootCmd.PersistentFlags().StringVarP(&Cfg.CNAME, "cname", "c", "", "cname for action")
	rootCmd.PersistentFlags().StringVar(&Cfg.CNAMEAlias, "cname-alias", "", "alias of CNAME content")
	rootCmd.PersistentFlags().StringSliceVarP(&Cfg.TXTRecords, "txt", "x", nil, "TXT record for action")
	rootCmd.PersistentFlags().StringSliceVar(&Cfg.DNSTypes, "dns-type", nil, "dns type for delete/list")
	rootCmd.PersistentFlags().IntVarP(&Cfg.TTL, "ttl", "t", 60, "ttl for record")

	// Custom Str2Bool pflag value for --proxied
	proxiedVal := config.Str2Bool{Value: &Cfg.Proxied}
	rootCmd.PersistentFlags().Var(&proxiedVal, "proxied", "It should be proxied")

	rootCmd.PersistentFlags().StringSliceVarP(&Cfg.Raws, "raw", "r", nil, "raw record for operation")
	rootCmd.PersistentFlags().StringVar(&Cfg.RawFile, "raw-file", "", "file stored raw for operation")
	rootCmd.PersistentFlags().StringSliceVar(&Cfg.RawAliases, "raw-alias", nil, "alias of raw content")
	rootCmd.PersistentFlags().StringVar(&Cfg.RawAliasFile, "raw-alias-file", "", "file stored raw for operation")
	rootCmd.PersistentFlags().StringVar(&Cfg.HTTPProxy, "http-proxy", "", "Custom HTTP proxy URL")
	rootCmd.PersistentFlags().StringVar(&Cfg.HTTPSProxy, "https-proxy", "", "Custom HTTPS proxy URL")
	rootCmd.PersistentFlags().BoolVarP(&Cfg.Version, "version", "v", false, "show version")

	// Legacy Command Modes (mapped as flags on root command)
	rootCmd.Flags().BoolVar(&Cfg.ListZone, "list-zone", false, "list all zones")
	rootCmd.Flags().BoolVar(&Cfg.ListZone, "list-zones", false, "list all zones (alias)")
	rootCmd.Flags().BoolVar(&Cfg.ListRecord, "list-record", false, "list records for specific zone")
	rootCmd.Flags().BoolVar(&Cfg.ListRecord, "list-records", false, "list records for specific zone (alias)")
	rootCmd.Flags().BoolVar(&Cfg.UpdateRecord, "update-record", false, "domain for update")
	rootCmd.Flags().BoolVar(&Cfg.UpdateRecord, "update-records", false, "domain for update (alias)")
	rootCmd.Flags().BoolVar(&Cfg.AddRecord, "add-record", false, "domain for add")
	rootCmd.Flags().BoolVar(&Cfg.AddRecord, "add-records", false, "domain for add (alias)")
	rootCmd.Flags().BoolVar(&Cfg.DeleteRecord, "delete-record", false, "domain for delete")
	rootCmd.Flags().BoolVar(&Cfg.DeleteRecord, "delete-records", false, "domain for delete (alias)")
}

// InterceptAndRouteArgs checks if legacy mode flags are present in os.Args.
// If so, it updates os.Args dynamically to redirect to subcommands.
func InterceptAndRouteArgs() {
	args := os.Args[1:]
	if len(args) == 0 {
		return
	}

	newArgs := []string{os.Args[0]}
	var routeTo string

	// Helper to check and strip command mode flags
	checkFlag := func(arg string) bool {
		switch arg {
		case "--list-zone", "--list-zones":
			routeTo = "zones list"
			return true
		case "--list-record", "--list-records":
			routeTo = "records list"
			return true
		case "--update-record", "--update-records":
			routeTo = "records update"
			return true
		case "--add-record", "--add-records":
			routeTo = "records add"
			return true
		case "--delete-record", "--delete-records":
			routeTo = "records delete"
			return true
		}
		return false
	}

	for i := 0; i < len(args); i++ {
		arg := args[i]
		if checkFlag(arg) {
			if i+1 < len(args) {
				next := strings.ToLower(args[i+1])
				if next == "false" || next == "no" || next == "0" || next == "f" || next == "n" {
					routeTo = ""
					i++ // Skip value
					continue
				} else if next == "true" || next == "yes" || next == "1" || next == "t" || next == "y" {
					i++ // Skip value
				}
			}
		} else if strings.Contains(arg, "=") {
			parts := strings.SplitN(arg, "=", 2)
			if checkFlag(parts[0]) {
				val := strings.ToLower(parts[1])
				if val == "false" || val == "no" || val == "0" || val == "f" || val == "n" {
					routeTo = ""
				}
			} else {
				newArgs = append(newArgs, arg)
			}
		} else {
			newArgs = append(newArgs, arg)
		}
	}

	if routeTo != "" {
		parts := strings.Split(routeTo, " ")
		os.Args = append(newArgs[:1], append(parts, newArgs[1:]...)...)
	} else {
		os.Args = newArgs
	}
}

// Execute executes the Cobra root command
func Execute() {
	InterceptAndRouteArgs()
	if err := rootCmd.Execute(); err != nil {
		fmt.Println(err)
		os.Exit(1)
	}
}
