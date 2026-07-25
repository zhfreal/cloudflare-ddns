package ipfinder

import (
	"context"
	"errors"
	"io"
	"net"
	"net/http"
	"strings"
	"time"
)

// IPFinder interface
type IPFinder interface {
	FindPublicIP(ctx context.Context, version int) (string, error)
}

// ConcreteIPFinder implements IPFinder
type ConcreteIPFinder struct {
	providers []string
}

// NewIPFinder returns a new IPFinder instance
func NewIPFinder(providers []string) *ConcreteIPFinder {
	if len(providers) == 0 {
		providers = []string{
			"https://api64.ipify.org/",
			"https://ip.seeip.org",
			"http://api.ip.sb/ip",
		}
	}
	return &ConcreteIPFinder{providers: providers}
}

// FindPublicIP queries multiple providers concurrently for the external IP.
// version should be 4 (IPv4) or 6 (IPv6) or 0 (any).
func (f *ConcreteIPFinder) FindPublicIP(ctx context.Context, version int) (string, error) {
	ctx, cancel := context.WithCancel(ctx)
	defer cancel()

	results := make(chan string, len(f.providers))
	errs := make(chan error, len(f.providers))

	for _, provider := range f.providers {
		go func(url string) {
			req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
			if err != nil {
				errs <- err
				return
			}
			resp, err := http.DefaultClient.Do(req)
			if err != nil {
				errs <- err
				return
			}
			defer resp.Body.Close()

			if resp.StatusCode != http.StatusOK {
				errs <- errors.New("non-200 status code")
				return
			}

			body, err := io.ReadAll(resp.Body)
			if err != nil {
				errs <- err
				return
			}

			ipStr := strings.TrimSpace(string(body))
			ip := net.ParseIP(ipStr)
			if ip == nil {
				errs <- errors.New("invalid IP response format")
				return
			}

			// Validate IP version if specified
			if version == 4 && ip.To4() == nil {
				errs <- errors.New("expected IPv4, got IPv6")
				return
			}
			if version == 6 && ip.To4() != nil {
				errs <- errors.New("expected IPv6, got IPv4")
				return
			}

			select {
			case results <- ipStr:
			case <-ctx.Done():
			}
		}(provider)
	}

	var lastErr error
	for i := 0; i < len(f.providers); i++ {
		select {
		case ip := <-results:
			return ip, nil
		case err := <-errs:
			lastErr = err
		case <-time.After(10 * time.Second):
			return "", errors.New("timeout resolving public IP")
		case <-ctx.Done():
			return "", ctx.Err()
		}
	}

	if lastErr != nil {
		return "", lastErr
	}
	return "", errors.New("all IP providers failed to resolve public IP")
}
