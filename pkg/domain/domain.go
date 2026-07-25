package domain

import (
	"sort"
	"strings"
)

// GetZoneName extracts the zone name from a domain
func GetZoneName(domain string, domainClass int) (int, string) {
	parts := strings.Split(domain, ".")
	var segments []string
	for _, p := range parts {
		trimmed := strings.ToLower(strings.TrimSpace(p))
		if trimmed != "" {
			segments = append(segments, trimmed)
		}
	}
	tLen := len(segments)
	if tLen < 2 {
		return 0, ""
	}
	if domainClass <= 0 {
		domainClass = tLen
	} else if domainClass <= 2 {
		domainClass = 2
	}
	if tLen < domainClass {
		domainClass = tLen
	}
	return domainClass, strings.Join(segments[tLen-domainClass:], ".")
}

// GetFullName joins domain and zoneName
func GetFullName(domain, zoneName string) string {
	domain = strings.ToLower(strings.Trim(domain, " ."))
	zoneName = strings.ToLower(strings.Trim(zoneName, " ."))
	if domain == "" || zoneName == "" {
		return ""
	}
	if domain == zoneName {
		return domain
	}
	if strings.HasSuffix(domain, "."+zoneName) {
		return domain
	}
	return domain + "." + zoneName
}

// SplitDomain splits domain into (prefix, zone) given a map of registered zones
func SplitDomain(domain string, zones map[string]bool) (prefix, zone string) {
	domain = strings.ToLower(strings.Trim(domain, " ."))
	if zones[domain] {
		return "", domain
	}
	// Direct string key iteration
	for z := range zones {
		if domain == z {
			return "", z
		}
		if strings.HasSuffix(domain, "."+z) {
			prefix = strings.TrimSuffix(domain, "."+z)
			prefix = strings.Trim(prefix, ".")
			return prefix, z
		}
	}
	return "", ""
}

// HasRootZone checks if domain has a root zone registered
func HasRootZone(domain string, zones map[string]bool) bool {
	domain = strings.ToLower(strings.Trim(domain, " ."))
	if zones[domain] {
		return true
	}
	for z := range zones {
		if domain == z || strings.HasSuffix(domain, "."+z) {
			return true
		}
	}
	return false
}

// SortZones sorts zones by segment count descending and alphabetically within count
func SortZones(zones []string) []string {
	if len(zones) == 0 {
		return []string{}
	}

	uniqueMap := make(map[string]bool)
	var uniqueList []string
	for _, z := range zones {
		trimmed := strings.Trim(z, " .")
		if trimmed != "" && !uniqueMap[trimmed] {
			uniqueMap[trimmed] = true
			uniqueList = append(uniqueList, trimmed)
		}
	}

	type zoneItem struct {
		name     string
		segments int
	}

	var items []zoneItem
	for _, z := range uniqueList {
		items = append(items, zoneItem{
			name:     z,
			segments: len(strings.Split(z, ".")),
		})
	}

	sort.Slice(items, func(i, j int) bool {
		if items[i].segments != items[j].segments {
			return items[i].segments > items[j].segments
		}
		return items[i].name < items[j].name
	})

	var sorted []string
	for _, item := range items {
		sorted = append(sorted, item.name)
	}
	return sorted
}
