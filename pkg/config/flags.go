package config

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"gopkg.in/yaml.v3"
)

// Str2Bool implements pflag.Value to parse custom boolean flags
type Str2Bool struct {
	Value *bool
}

func (s *Str2Bool) String() string {
	if s.Value == nil {
		return "false"
	}
	return fmt.Sprintf("%v", *s.Value)
}

func (s *Str2Bool) Set(v string) error {
	val := strings.ToLower(strings.TrimSpace(v))
	if val == "" || val == "yes" || val == "true" || val == "t" || val == "y" || val == "1" {
		t := true
		s.Value = &t
		return nil
	} else if val == "no" || val == "false" || val == "f" || val == "n" || val == "0" {
		f := false
		s.Value = &f
		return nil
	}
	return fmt.Errorf("Bool value expected.")
}

func (s *Str2Bool) Type() string {
	return "str2bool"
}

// Config represents all parsed parameters
type Config struct {
	Email        string
	APIKey       string
	APIToken     string
	Zones        []string
	Domains      []string
	Aliases      []string
	IPv4Addrs    []string
	IPv6Addrs    []string
	CNAME        string
	CNAMEAlias   string
	TXTRecords   []string
	DNSTypes     []string
	IDs          []string
	TTL          int
	Proxied      bool
	Raws         []string
	RawFile      string
	RawAliases   []string
	RawAliasFile string
	HTTPProxy    string
	HTTPSProxy   string
	Version      bool

	// Command Modes
	ListZone     bool
	ListRecord   bool
	UpdateRecord bool
	AddRecord    bool
	DeleteRecord bool
}

// LoadFromFile loads default config values from a YAML file
func LoadFromFile(c *Config) {
	home, err := os.UserHomeDir()
	if err == nil {
		path := filepath.Join(home, ".cloudflare-ddns.yaml")
		loadYAML(path, c)
	}
	loadYAML("/etc/cloudflare-ddns.yaml", c)
}

func loadYAML(path string, c *Config) {
	file, err := os.Open(path)
	if err != nil {
		return
	}
	defer file.Close()

	decoder := yaml.NewDecoder(file)
	var fileCfg struct {
		APIToken   string `yaml:"api_token"`
		Email      string `yaml:"email"`
		APIKey     string `yaml:"api_key"`
		TTL        int    `yaml:"ttl"`
		Proxied    *bool  `yaml:"proxied"`
		HTTPProxy  string `yaml:"http_proxy"`
		HTTPSProxy string `yaml:"https_proxy"`
	}

	if err := decoder.Decode(&fileCfg); err == nil {
		if fileCfg.APIToken != "" && c.APIToken == "" {
			c.APIToken = fileCfg.APIToken
		}
		if fileCfg.Email != "" && c.Email == "" {
			c.Email = fileCfg.Email
		}
		if fileCfg.APIKey != "" && c.APIKey == "" {
			c.APIKey = fileCfg.APIKey
		}
		if fileCfg.TTL > 0 && c.TTL == 60 { // 60 is default
			c.TTL = fileCfg.TTL
		}
		if fileCfg.Proxied != nil && !c.Proxied {
			c.Proxied = *fileCfg.Proxied
		}
		if fileCfg.HTTPProxy != "" && c.HTTPProxy == "" {
			c.HTTPProxy = fileCfg.HTTPProxy
		}
		if fileCfg.HTTPSProxy != "" && c.HTTPSProxy == "" {
			c.HTTPSProxy = fileCfg.HTTPSProxy
		}
	}
}

// ResolveEnvVars populates config fields from environment variables if not set
func ResolveEnvVars(c *Config) {
	if c.APIToken == "" {
		if t := os.Getenv("CLOUDFLARE_API_TOKEN"); t != "" {
			c.APIToken = t
		} else if t := os.Getenv("CF_API_TOKEN"); t != "" {
			c.APIToken = t
		}
	}
	if c.Email == "" {
		if e := os.Getenv("CLOUDFLARE_EMAIL"); e != "" {
			c.Email = e
		} else if e := os.Getenv("CF_EMAIL"); e != "" {
			c.Email = e
		}
	}
	if c.APIKey == "" {
		if k := os.Getenv("CLOUDFLARE_API_KEY"); k != "" {
			c.APIKey = k
		} else if k := os.Getenv("CF_API_KEY"); k != "" {
			c.APIKey = k
		}
	}
	if c.HTTPProxy == "" {
		c.HTTPProxy = os.Getenv("HTTP_PROXY")
	}
	if c.HTTPSProxy == "" {
		c.HTTPSProxy = os.Getenv("HTTPS_PROXY")
	}
}
