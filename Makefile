.PHONY: help build build-all build-release clean test docker check

BINARY_NAME=cloudflare-ddns
VERSION=26.07.25

help:
	@echo "Available commands:"
	@echo "  make build         - Build local binary (output to dist/)"
	@echo "  make build-all     - Cross-compile all targets for release"
	@echo "  make build-release - Alias for build-all"
	@echo "  make test          - Run Go tests"
	@echo "  make clean         - Remove build artifacts"
	@echo "  make docker        - Build Docker container"

build:
	mkdir -p dist
	go build -ldflags "-X github.com/zhfreal/cloudflare-ddns/pkg/version.Version=$(VERSION) -X github.com/zhfreal/cloudflare-ddns/pkg/version.GitCommit=$$(git rev-parse --short HEAD 2>/dev/null || echo 'unknown') -X github.com/zhfreal/cloudflare-ddns/pkg/version.BuildDate=$$(date -u +%Y-%m-%dT%H:%M:%SZ)" -o dist/$(BINARY_NAME) ./cmd/cloudflare-ddns

build-all: clean
	mkdir -p dist
	GOOS=linux GOARCH=amd64 go build -ldflags "-X github.com/zhfreal/cloudflare-ddns/pkg/version.Version=$(VERSION)" -o dist/$(BINARY_NAME)-linux-amd64 ./cmd/cloudflare-ddns
	GOOS=linux GOARCH=amd64 GOAMD64=v3 go build -ldflags "-X github.com/zhfreal/cloudflare-ddns/pkg/version.Version=$(VERSION)" -o dist/$(BINARY_NAME)-linux-amd64v3 ./cmd/cloudflare-ddns
	GOOS=linux GOARCH=arm64 go build -ldflags "-X github.com/zhfreal/cloudflare-ddns/pkg/version.Version=$(VERSION)" -o dist/$(BINARY_NAME)-linux-arm64 ./cmd/cloudflare-ddns
	GOOS=darwin GOARCH=amd64 go build -ldflags "-X github.com/zhfreal/cloudflare-ddns/pkg/version.Version=$(VERSION)" -o dist/$(BINARY_NAME)-darwin-amd64 ./cmd/cloudflare-ddns
	GOOS=darwin GOARCH=arm64 go build -ldflags "-X github.com/zhfreal/cloudflare-ddns/pkg/version.Version=$(VERSION)" -o dist/$(BINARY_NAME)-darwin-arm64 ./cmd/cloudflare-ddns
	GOOS=windows GOARCH=amd64 go build -ldflags "-X github.com/zhfreal/cloudflare-ddns/pkg/version.Version=$(VERSION)" -o dist/$(BINARY_NAME)-windows-amd64.exe ./cmd/cloudflare-ddns
	GOOS=windows GOARCH=amd64 GOAMD64=v3 go build -ldflags "-X github.com/zhfreal/cloudflare-ddns/pkg/version.Version=$(VERSION)" -o dist/$(BINARY_NAME)-windows-amd64v3.exe ./cmd/cloudflare-ddns
	GOOS=windows GOARCH=arm64 go build -ldflags "-X github.com/zhfreal/cloudflare-ddns/pkg/version.Version=$(VERSION)" -o dist/$(BINARY_NAME)-windows-arm64.exe ./cmd/cloudflare-ddns

build-release: build-all

test:
	go test -v ./...

clean:
	rm -f $(BINARY_NAME)
	rm -rf dist/

docker:
	docker build -t $(BINARY_NAME):latest .

check: test build
	@echo "All checks passed!"
