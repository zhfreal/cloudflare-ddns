.PHONY: help build build-all build-release clean test docker check

BINARY_NAME=cloudflare-ddns
VERSION=26.07.25

GIT_COMMIT=$(shell git rev-parse --short HEAD 2>/dev/null || echo 'unknown')
BUILD_DATE=$(shell date -u +%Y-%m-%dT%H:%M:%SZ)
LDFLAGS=-ldflags "-s -w -X github.com/zhfreal/cloudflare-ddns/pkg/version.Version=$(VERSION) -X github.com/zhfreal/cloudflare-ddns/pkg/version.GitCommit=$(GIT_COMMIT) -X github.com/zhfreal/cloudflare-ddns/pkg/version.BuildDate=$(BUILD_DATE)"

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
	go build $(LDFLAGS) -o dist/$(BINARY_NAME) ./cmd/cloudflare-ddns
	@if command -v upx >/dev/null 2>&1; then \
		echo "Compressing local binary with UPX..."; \
		upx --best dist/$(BINARY_NAME); \
	fi

build-all: clean
	mkdir -p dist
	GOOS=linux GOARCH=amd64 go build $(LDFLAGS) -o dist/$(BINARY_NAME)-linux-amd64 ./cmd/cloudflare-ddns
	GOOS=linux GOARCH=amd64 GOAMD64=v3 go build $(LDFLAGS) -o dist/$(BINARY_NAME)-linux-amd64v3 ./cmd/cloudflare-ddns
	GOOS=linux GOARCH=arm64 go build $(LDFLAGS) -o dist/$(BINARY_NAME)-linux-arm64 ./cmd/cloudflare-ddns
	GOOS=darwin GOARCH=amd64 go build $(LDFLAGS) -o dist/$(BINARY_NAME)-darwin-amd64 ./cmd/cloudflare-ddns
	GOOS=darwin GOARCH=arm64 go build $(LDFLAGS) -o dist/$(BINARY_NAME)-darwin-arm64 ./cmd/cloudflare-ddns
	GOOS=windows GOARCH=amd64 go build $(LDFLAGS) -o dist/$(BINARY_NAME)-windows-amd64.exe ./cmd/cloudflare-ddns
	GOOS=windows GOARCH=amd64 GOAMD64=v3 go build $(LDFLAGS) -o dist/$(BINARY_NAME)-windows-amd64v3.exe ./cmd/cloudflare-ddns
	GOOS=windows GOARCH=arm64 go build $(LDFLAGS) -o dist/$(BINARY_NAME)-windows-arm64.exe ./cmd/cloudflare-ddns
	@if command -v upx >/dev/null 2>&1; then \
		echo "Compressing supported release binaries with UPX..."; \
		upx --best dist/$(BINARY_NAME)-linux-amd64 dist/$(BINARY_NAME)-linux-amd64v3 dist/$(BINARY_NAME)-linux-arm64 dist/$(BINARY_NAME)-windows-amd64.exe dist/$(BINARY_NAME)-windows-amd64v3.exe || true; \
	fi

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
