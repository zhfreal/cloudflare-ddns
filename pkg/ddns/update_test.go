package ddns

import (
	"context"
	"testing"

	"github.com/zhfreal/cloudflare-ddns/pkg/cfclient"
)

type mockCloudflareAPI struct {
	Zones   []cfclient.Zone
	Records []cfclient.DNSRecord

	Created []cfclient.DNSRecord
	Updated []struct {
		ID     string
		Record cfclient.DNSRecord
	}
	Deleted []string
}

func (m *mockCloudflareAPI) ListZones(ctx context.Context) ([]cfclient.Zone, error) {
	return m.Zones, nil
}

func (m *mockCloudflareAPI) ListDNSRecords(ctx context.Context, zoneID string, domainFilter string) ([]cfclient.DNSRecord, error) {
	return m.Records, nil
}

func (m *mockCloudflareAPI) CreateDNSRecord(ctx context.Context, zoneID string, record cfclient.DNSRecord) (*cfclient.DNSRecord, error) {
	m.Created = append(m.Created, record)
	record.ID = "new_id"
	return &record, nil
}

func (m *mockCloudflareAPI) UpdateDNSRecord(ctx context.Context, zoneID string, recordID string, record cfclient.DNSRecord) (*cfclient.DNSRecord, error) {
	m.Updated = append(m.Updated, struct {
		ID     string
		Record cfclient.DNSRecord
	}{recordID, record})
	record.ID = recordID
	return &record, nil
}

func (m *mockCloudflareAPI) DeleteDNSRecord(ctx context.Context, zoneID string, recordID string) (*cfclient.DNSRecordDeleteResponse, error) {
	m.Deleted = append(m.Deleted, recordID)
	return &cfclient.DNSRecordDeleteResponse{
		ID: recordID,
	}, nil
}

func TestUpdateReconciliation(t *testing.T) {
	mockAPI := &mockCloudflareAPI{
		Zones: []cfclient.Zone{
			{ID: "zone123", Name: "example.com"},
		},
		Records: []cfclient.DNSRecord{
			// An extra record on sub.example.com that should be re-purposed
			{ID: "rec1", Name: "sub.example.com", Type: "A", Content: "9.9.9.9", TTL: 60, Proxied: false},
			// An in-place record on sub.example.com that needs a TTL/Proxied update
			{ID: "rec2", Name: "sub.example.com", Type: "A", Content: "1.2.3.4", TTL: 60, Proxied: false},
		},
	}

	client := &cfclient.Client{
		Zones: map[string]*cfclient.ZoneMeta{
			"example.com": {
				ID:      "zone123",
				Records: make(map[string]map[string]map[string]string),
			},
		},
		DNSRecords: make(map[string]*cfclient.DNSRecord),
	}
	client.SetAPIClient(mockAPI)

	desired := cfclient.DesiredRecords{
		"example.com": {
			"sub": {
				cfclient.RecordTypeA: {
					"1.2.3.4": cfclient.RecordOpts{TTL: 300, Proxied: true},  // Should trigger Phase 3: Update-in-Place
					"5.6.7.8": cfclient.RecordOpts{TTL: 60, Proxied: false}, // Should trigger Phase 4: Re-purpose "rec1"
				},
			},
		},
	}

	err := UpdateRecordsNew(context.Background(), client, desired)
	if err != nil {
		t.Fatalf("unexpected update error: %v", err)
	}

	// 1. Assert updates
	updatedCount := 0
	for _, u := range mockAPI.Updated {
		if u.ID == "rec2" {
			updatedCount++
			// TTL is overridden to 1 because Proxied is true
			if u.Record.TTL != 1 || !u.Record.Proxied {
				t.Errorf("expected rec2 to be updated to TTL=1 and Proxied=true")
			}
		}
		if u.ID == "rec1" {
			// 2. Assert re-purposing (rec1 updated to new content)
			updatedCount++
			if u.Record.Content != "5.6.7.8" || u.Record.Name != "sub.example.com" {
				t.Errorf("expected rec1 to be re-purposed to sub.example.com with 5.6.7.8")
			}
		}
	}

	if updatedCount != 2 {
		t.Errorf("expected 2 records to be updated, got %d", updatedCount)
	}

	// 3. Assert no surplus deletes and no new creations since everything was resolved by re-purposing
	if len(mockAPI.Deleted) != 0 {
		t.Errorf("expected 0 deletes, got %d", len(mockAPI.Deleted))
	}
	if len(mockAPI.Created) != 0 {
		t.Errorf("expected 0 new creations, got %d", len(mockAPI.Created))
	}
}
