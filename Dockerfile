FROM golang:1.22-alpine AS builder
WORKDIR /app
COPY . .
RUN go mod download
RUN go build -o cloudflare-ddns ./cmd/cloudflare-ddns

FROM alpine:latest
RUN apk --no-cache add ca-certificates
WORKDIR /app
COPY --from=builder /app/cloudflare-ddns .
ENTRYPOINT ["./cloudflare-ddns"]
