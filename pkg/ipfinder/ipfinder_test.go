package ipfinder

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestIPFinderFallback(t *testing.T) {
	// First server returns error
	s1 := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "internal server error", http.StatusInternalServerError)
	}))
	defer s1.Close()

	// Second server returns invalid IP
	s2 := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte("invalid-ip"))
	}))
	defer s2.Close()

	// Third server returns valid IP
	s3 := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte("1.2.3.4"))
	}))
	defer s3.Close()

	finder := NewIPFinder([]string{s1.URL, s2.URL, s3.URL})
	ip, err := finder.FindPublicIP(context.Background(), 4)
	if err != nil {
		t.Fatalf("unexpected error resolving IP: %v", err)
	}

	if ip != "1.2.3.4" {
		t.Errorf("expected 1.2.3.4, got %s", ip)
	}
}
