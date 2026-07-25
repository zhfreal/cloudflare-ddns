package config

import (
	"regexp"
	"strings"
)

var splitterRegex = regexp.MustCompile(`[;,|\s]+`)

// SplitContent splits a string based on the Python splitter regex [;,|\s]+
func SplitContent(content string) []string {
	parts := splitterRegex.Split(content, -1)
	var result []string
	seen := make(map[string]bool)
	for _, part := range parts {
		p := strings.TrimSpace(part)
		if p != "" && !seen[p] {
			seen[p] = true
			result = append(result, p)
		}
	}
	return result
}

// SplitContentList implements Python's split_content_list.
// If dnsType is TXT, it preserves items verbatim and does not split them by delimiters.
func SplitContentList(contentList []string, dnsType string) []string {
	var result []string
	seen := make(map[string]bool)

	for _, item := range contentList {
		if strings.ToUpper(dnsType) == "TXT" {
			trimmed := strings.TrimSpace(item)
			if trimmed != "" && !seen[trimmed] {
				seen[trimmed] = true
				result = append(result, trimmed)
			}
		} else {
			parts := SplitContent(item)
			for _, part := range parts {
				if !seen[part] {
					seen[part] = true
					result = append(result, part)
				}
			}
		}
	}
	return result
}
