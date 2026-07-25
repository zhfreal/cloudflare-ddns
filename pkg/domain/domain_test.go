package domain

import (
	"testing"
)

func TestSplitDomain(t *testing.T) {
	zones := map[string]bool{
		"example.com":      true,
		"sub.domain.co.uk": true,
	}

	tests := []struct {
		input  string
		prefix string
		zone   string
	}{
		{"example.com", "", "example.com"},
		{"www.example.com", "www", "example.com"},
		{"a.b.c.example.com", "a.b.c", "example.com"},
		{"not-a-zone.com", "", ""},
	}

	for _, tc := range tests {
		p, z := SplitDomain(tc.input, zones)
		if p != tc.prefix || z != tc.zone {
			t.Errorf("expected (%q, %q) for %s, got (%q, %q)", tc.prefix, tc.zone, tc.input, p, z)
		}
	}
}

func TestHasRootZone(t *testing.T) {
	zones := map[string]bool{
		"example.com": true,
	}

	if !HasRootZone("example.com", zones) {
		t.Errorf("expected true for example.com")
	}
	if !HasRootZone("sub.example.com", zones) {
		t.Errorf("expected true for sub.example.com")
	}
	if HasRootZone("otherdomain.org", zones) {
		t.Errorf("expected false for otherdomain.org")
	}
}

func TestGetFullName(t *testing.T) {
	if GetFullName("example.com", "example.com") != "example.com" {
		t.Errorf("GetFullName failed")
	}
	if GetFullName("www", "example.com") != "www.example.com" {
		t.Errorf("GetFullName failed")
	}
	if GetFullName("www.example.com", "example.com") != "www.example.com" {
		t.Errorf("GetFullName failed")
	}
}
