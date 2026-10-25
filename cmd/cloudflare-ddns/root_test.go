package main

import (
	"os"
	"testing"

	"github.com/zhfreal/cloudflare-ddns/pkg/config"
)

func TestInterceptAndRouteArgsProxied(t *testing.T) {
	origArgs := os.Args
	defer func() { os.Args = origArgs }()

	tests := []struct {
		name     string
		input    []string
		expected []string
	}{
		{
			name:     "add-record with proxied=true",
			input:    []string{"cloudflare-ddns", "--add-record", "--zone", "example.com", "--proxied=true"},
			expected: []string{"cloudflare-ddns", "records", "add", "--zone", "example.com", "--proxied=true"},
		},
		{
			name:     "update-record with proxied=true",
			input:    []string{"cloudflare-ddns", "--update-record", "--zone", "example.com", "--proxied=true"},
			expected: []string{"cloudflare-ddns", "records", "update", "--zone", "example.com", "--proxied=true"},
		},
		{
			name:     "update-records alias with proxied=true",
			input:    []string{"cloudflare-ddns", "--update-records", "--zone", "example.com", "--proxied=true"},
			expected: []string{"cloudflare-ddns", "records", "update", "--zone", "example.com", "--proxied=true"},
		},
		{
			name:     "space-separated proxied true",
			input:    []string{"cloudflare-ddns", "--add-record", "--proxied", "true", "--zone", "example.com"},
			expected: []string{"cloudflare-ddns", "records", "add", "--proxied=true", "--zone", "example.com"},
		},
		{
			name:     "space-separated proxied false",
			input:    []string{"cloudflare-ddns", "records", "update", "--proxied", "false", "--zone", "example.com"},
			expected: []string{"cloudflare-ddns", "records", "update", "--proxied=false", "--zone", "example.com"},
		},
		{
			name:     "standalone proxied",
			input:    []string{"cloudflare-ddns", "--add-record", "--proxied", "--zone", "example.com"},
			expected: []string{"cloudflare-ddns", "records", "add", "--proxied", "--zone", "example.com"},
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			os.Args = append([]string(nil), tc.input...)
			InterceptAndRouteArgs()
			if len(os.Args) != len(tc.expected) {
				t.Fatalf("expected args len %d, got %d: %v", len(tc.expected), len(os.Args), os.Args)
			}
			for i := range os.Args {
				if os.Args[i] != tc.expected[i] {
					t.Errorf("arg %d: expected %s, got %s", i, tc.expected[i], os.Args[i])
				}
			}
		})
	}
}

func TestProxiedFlagParsing(t *testing.T) {
	tests := []struct {
		name     string
		args     []string
		expected bool
	}{
		{
			name:     "proxied=true",
			args:     []string{"records", "add", "--proxied=true"},
			expected: true,
		},
		{
			name:     "proxied standalone",
			args:     []string{"records", "add", "--proxied"},
			expected: true,
		},
		{
			name:     "proxied=false",
			args:     []string{"records", "add", "--proxied=false"},
			expected: false,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			Cfg = config.Config{}
			rootCmd.SetArgs(tc.args)
			// Parse flags without executing RunE
			err := rootCmd.ParseFlags(tc.args)
			if err != nil {
				t.Fatalf("unexpected ParseFlags error: %v", err)
			}
			if Cfg.Proxied != tc.expected {
				t.Errorf("expected Cfg.Proxied=%t, got %t", tc.expected, Cfg.Proxied)
			}
			if !Cfg.ProxiedSet {
				t.Errorf("expected Cfg.ProxiedSet to be true")
			}
		})
	}
}
