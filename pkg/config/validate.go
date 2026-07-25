package config

import (
	"errors"
)

// Validate validates the configuration options based on the Python script's exclusivity rules
func Validate(c *Config) error {
	// 1. Check authentication credentials
	if c.APIToken == "" {
		if c.Email == "" {
			return errors.New("No email or API token provided!")
		}
		if c.APIKey == "" {
			return errors.New("No API Key!")
		}
	}

	// 2. Validate Command Modes
	modeCount := 0
	if c.ListZone {
		modeCount++
	}
	if c.ListRecord {
		modeCount++
	}
	if c.UpdateRecord {
		modeCount++
	}
	if c.AddRecord {
		modeCount++
	}
	if c.DeleteRecord {
		modeCount++
	}

	if modeCount == 0 {
		return errors.New("No valid cmd provided!")
	}
	if modeCount > 1 {
		return errors.New("Please select only one command mode!")
	}

	// If listing zones, no further validation of domain/record flags is needed
	if c.ListZone {
		return nil
	}

	// 3. Flag Exclusivity Matrix (Non-ListRecord modes only)
	if !c.ListRecord {
		hasIP := len(c.IPv4Addrs) > 0 || len(c.IPv6Addrs) > 0
		hasCNAME := c.CNAME != "" || c.CNAMEAlias != ""
		hasTXT := len(c.TXTRecords) > 0
		hasRaw := len(c.Raws) > 0 || c.RawFile != ""
		hasRawAlias := len(c.RawAliases) > 0 || c.RawAliasFile != ""

		if hasIP {
			if hasCNAME {
				return errors.New("Please do not use \"--cname\" or \"--cname-alias\" with \"--ipv4-addr\" or \"--ipv6-addr\"")
			}
			if hasTXT {
				return errors.New("Please do not use \"--txt\" with \"--ipv4-addr\" or \"--ipv6-addr\"")
			}
			if hasRaw || hasRawAlias {
				return errors.New("Please do not use \"--raw\", \"--raw-alias\", \"--raw-file\" or \"--raw-alias-file\" with \"--ipv4-addr\" or \"--ipv6-addr\"")
			}
			if err := validateZoneDomainAlias(c); err != nil {
				return err
			}
		} else if hasCNAME {
			if hasTXT {
				return errors.New("Please do not use \"--txt\" with \"--cname\" or \"--cname-alias\"")
			}
			if hasRaw || hasRawAlias {
				return errors.New("Please do not use \"--raw\", \"--raw-alias\", \"--raw-file\" or \"--raw-alias-file\" with \"--cname\" or \"--cname-alias\"")
			}
			if c.CNAMEAlias != "" {
				if len(c.Zones) == 0 || len(c.Aliases) == 0 {
					return errors.New("Please use \"--zone\", \"--alias\" with \"--cname-alias\"")
				}
				if len(c.Domains) > 0 {
					return errors.New("Please do not use \"--domain\" with \"--cname-alias\"")
				}
			} else {
				if err := validateZoneDomainAlias(c); err != nil {
					return err
				}
			}
		} else if hasTXT {
			if hasRaw || hasRawAlias {
				return errors.New("Please do not use \"--raw\", \"--raw-alias\", \"--raw-file\" or \"--raw-alias-file\" with \"--txt\"")
			}
			if err := validateZoneDomainAlias(c); err != nil {
				return err
			}
		} else if hasRaw || hasRawAlias {
			if len(c.Aliases) > 0 || len(c.Domains) > 0 {
				return errors.New("Please do not use \"--alias\" or \"--domain\" with \"--raw\", \"--raw-alias\", \"--raw-file\" or \"--raw-alias-file\"")
			}
			if len(c.Zones) == 0 {
				return errors.New("Please use \"--zone\" with \"--raw\", \"--raw-alias\", \"--raw-file\" or \"--raw-alias-file\"")
			}
			if hasRaw && hasRawAlias {
				return errors.New("Please do not use \"--raw\" or \"--raw-file\" with \"--raw-alias\" or \"--raw-alias-file\" at the same time.")
			}
		}
	}

	return nil
}

func validateZoneDomainAlias(c *Config) error {
	if len(c.Zones) > 0 {
		if len(c.Aliases) == 0 {
			return errors.New("Please use \"--alias\" with \"--zone\"")
		}
		if len(c.Domains) > 0 {
			return errors.New("Please do not use \"--domain\" with \"--zone\"")
		}
	} else if len(c.Domains) == 0 {
		return errors.New("Please use \"--zone\" with \"--alias\" or just use \"--domain\"")
	}
	return nil
}
