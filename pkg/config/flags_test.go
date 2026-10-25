package config

import (
	"testing"
)

func TestStr2Bool(t *testing.T) {
	tests := []struct {
		input    string
		expected bool
		wantErr  bool
	}{
		{"true", true, false},
		{"True", true, false},
		{"yes", true, false},
		{"1", true, false},
		{"t", true, false},
		{"false", false, false},
		{"False", false, false},
		{"no", false, false},
		{"0", false, false},
		{"f", false, false},
		{"invalid", false, true},
	}

	for _, tc := range tests {
		var b bool
		var isSet bool
		s := Str2Bool{Value: &b, IsSet: &isSet}
		err := s.Set(tc.input)
		if tc.wantErr {
			if err == nil {
				t.Errorf("expected error for %s, got nil", tc.input)
			}
		} else {
			if err != nil {
				t.Errorf("unexpected error for %s: %v", tc.input, err)
			}
			// Verify that underlying pointed-to bool is updated
			if b != tc.expected {
				t.Errorf("expected underlying bool %t, got %t for %s", tc.expected, b, tc.input)
			}
			if *s.Value != tc.expected {
				t.Errorf("expected %t, got %t for %s", tc.expected, *s.Value, tc.input)
			}
			if !isSet {
				t.Errorf("expected isSet to be true after Set(%s)", tc.input)
			}
		}
		if !s.IsBoolFlag() {
			t.Errorf("expected IsBoolFlag to be true")
		}
	}
}

func TestParseRawLine(t *testing.T) {
	tests := []struct {
		input    string
		expected []string
	}{
		{"sub,A,1.2.3.4,60,false", []string{"sub", "A", "1.2.3.4", "60", "false"}},
		{"sub;AAAA;2001:db8::1;300;true", []string{"sub", "AAAA", "2001:db8::1", "300", "true"}},
		{"sub|CNAME|target.com|auto|false", []string{"sub", "CNAME", "target.com", "auto", "false"}},
	}

	for _, tc := range tests {
		res, err := ParseRawLine(tc.input)
		if err != nil {
			t.Fatalf("unexpected error parsing %s: %v", tc.input, err)
		}
		if len(res) != len(tc.expected) {
			t.Fatalf("expected len %d, got %d for %s", len(tc.expected), len(res), tc.input)
		}
		for i := range res {
			if res[i] != tc.expected[i] {
				t.Errorf("expected item %d to be %s, got %s for %s", i, tc.expected[i], res[i], tc.input)
			}
		}
	}
}

func TestSplitContentList(t *testing.T) {
	res := SplitContentList([]string{"1.1.1.1, 2.2.2.2", "3.3.3.3"}, "A")
	expected := map[string]bool{"1.1.1.1": true, "2.2.2.2": true, "3.3.3.3": true}
	if len(res) != 3 {
		t.Errorf("expected length 3, got %d", len(res))
	}
	for _, val := range res {
		if !expected[val] {
			t.Errorf("unexpected value in split result: %s", val)
		}
	}

	txtRes := SplitContentList([]string{"v=spf1 include:_spf.google.com ~all"}, "TXT")
	if len(txtRes) != 1 || txtRes[0] != "v=spf1 include:_spf.google.com ~all" {
		t.Errorf("expected spf TXT record to be kept verbatim, got %+v", txtRes)
	}
}
