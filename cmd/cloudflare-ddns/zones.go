package main

import (
	"context"
	"fmt"
	"os"

	"github.com/spf13/cobra"
	"github.com/zhfreal/cloudflare-ddns/pkg/cfclient"
	"github.com/zhfreal/cloudflare-ddns/pkg/config"
	"github.com/zhfreal/cloudflare-ddns/pkg/ddns"
)

var zonesCmd = &cobra.Command{
	Use:   "zones",
	Short: "Manage zones in Cloudflare",
}

var zonesListCmd = &cobra.Command{
	Use:     "list",
	Aliases: []string{"list-zone", "list-zones"},
	Short:   "List all registered zones",
	RunE: func(cmd *cobra.Command, args []string) error {
		Cfg.ListZone = true

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

		ddns.ListZones(client)
		return nil
	},
}

func init() {
	zonesCmd.AddCommand(zonesListCmd)
	rootCmd.AddCommand(zonesCmd)
}
