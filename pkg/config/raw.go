package config

import (
	"encoding/csv"
	"fmt"
	"regexp"
	"strconv"
	"strings"

	"github.com/google/shlex"
)

// ParseRawLine parses a single raw record line with delimiter auto-detection
func ParseRawLine(raw string) ([]string, error) {
	var delimiter rune = ','
	if strings.Contains(raw, ";") && !strings.Contains(raw, ",") {
		delimiter = ';'
	} else if strings.Contains(raw, "|") && !strings.Contains(raw, ",") {
		delimiter = '|'
	} else if !strings.ContainsAny(raw, ",;|") {
		// Try shlex split
		parts, err := shlex.Split(raw)
		if err == nil && len(parts) > 0 {
			return parts, nil
		}
	}

	r := csv.NewReader(strings.NewReader(raw))
	r.Comma = delimiter
	r.TrimLeadingSpace = true
	record, err := r.Read()
	if err != nil {
		// Fallback to split using whitespace/delimiters regex
		re := regexp.MustCompile(`[;,|\s]+`)
		parts := re.Split(raw, -1)
		var result []string
		for _, part := range parts {
			if part != "" {
				result = append(result, part)
			}
		}
		return result, nil
	}
	return record, nil
}

// ParseTTL parses the TTL value, mapping "auto" to 1
func ParseTTL(ttlStr string) (int, error) {
	ttlStr = strings.ToLower(strings.TrimSpace(ttlStr))
	if ttlStr == "auto" {
		return 1, nil
	}
	ttl, err := strconv.Atoi(ttlStr)
	if err != nil {
		return 0, fmt.Errorf("invalid ttl %s", ttlStr)
	}
	return ttl, nil
}
