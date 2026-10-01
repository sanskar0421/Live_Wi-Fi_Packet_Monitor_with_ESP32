#include <Arduino.h>
#include <WiFi.h>
#include <esp_wifi.h>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>

namespace {
constexpr uint8_t kStartMagic[] = {0xAA, 0xBB, 0xCC, 0xDD};
constexpr uint16_t kMaxPacketLength = 2500;
constexpr UBaseType_t kQueueDepth = 8;
constexpr uint32_t kChannelDwellMs = 250;

struct PacketBuffer {
	uint16_t length;
	uint8_t bytes[kMaxPacketLength];
};

PacketBuffer packetBuffers[kQueueDepth];
QueueHandle_t freeBuffers;
QueueHandle_t readyBuffers;
PacketBuffer *activeBuffer = nullptr;
uint8_t frameHeader[6];
size_t headerOffset = 0;
size_t packetOffset = 0;
uint8_t currentChannel = 1;
uint32_t lastChannelChange = 0;

void promiscuousReceive(void *buffer, wifi_promiscuous_pkt_type_t) {
	const auto *packet = static_cast<const wifi_promiscuous_pkt_t *>(buffer);
	const uint16_t packetLength = packet->rx_ctrl.sig_len;
	if (packetLength == 0 || packetLength > kMaxPacketLength) {
		return;
	}

	PacketBuffer *destination = nullptr;
	if (xQueueReceive(freeBuffers, &destination, 0) != pdTRUE) {
		return;
	}

	destination->length = packetLength;
	memcpy(destination->bytes, packet->payload, packetLength);
	if (xQueueSend(readyBuffers, &destination, 0) != pdTRUE) {
		xQueueSend(freeBuffers, &destination, 0);
	}
}

void beginNextFrame() {
	if (activeBuffer != nullptr || xQueueReceive(readyBuffers, &activeBuffer, 0) != pdTRUE) {
		return;
	}

	memcpy(frameHeader, kStartMagic, sizeof(kStartMagic));
	frameHeader[4] = static_cast<uint8_t>(activeBuffer->length & 0xFF);
	frameHeader[5] = static_cast<uint8_t>(activeBuffer->length >> 8);
	headerOffset = 0;
	packetOffset = 0;
}

void transmitAvailableBytes() {
	beginNextFrame();
	if (activeBuffer == nullptr) {
		return;
	}

	const int available = Serial.availableForWrite();
	if (available <= 0) {
		return;
	}

	if (headerOffset < sizeof(frameHeader)) {
		const size_t remaining = sizeof(frameHeader) - headerOffset;
		const size_t count = min(remaining, static_cast<size_t>(available));
		headerOffset += Serial.write(frameHeader + headerOffset, count);
		return;
	}

	const size_t remaining = activeBuffer->length - packetOffset;
	const size_t count = min(remaining, static_cast<size_t>(available));
	packetOffset += Serial.write(activeBuffer->bytes + packetOffset, count);
	if (packetOffset == activeBuffer->length) {
		xQueueSend(freeBuffers, &activeBuffer, 0);
		activeBuffer = nullptr;
	}
}
}  // namespace

void setup() {
	Serial.begin(921600);

	freeBuffers = xQueueCreate(kQueueDepth, sizeof(PacketBuffer *));
	readyBuffers = xQueueCreate(kQueueDepth, sizeof(PacketBuffer *));
	if (freeBuffers == nullptr || readyBuffers == nullptr) {
		return;
	}
	for (UBaseType_t index = 0; index < kQueueDepth; ++index) {
		PacketBuffer *buffer = &packetBuffers[index];
		xQueueSend(freeBuffers, &buffer, 0);
	}

	WiFi.mode(WIFI_STA);
	esp_wifi_set_promiscuous(false);
	esp_wifi_set_channel(currentChannel, WIFI_SECOND_CHAN_NONE);
	esp_wifi_set_promiscuous_rx_cb(&promiscuousReceive);
	esp_wifi_set_promiscuous(true);
	lastChannelChange = millis();
}

void loop() {
	const uint32_t now = millis();
	if (static_cast<uint32_t>(now - lastChannelChange) >= kChannelDwellMs) {
		currentChannel = currentChannel == 14 ? 1 : currentChannel + 1;
		esp_wifi_set_channel(currentChannel, WIFI_SECOND_CHAN_NONE);
		lastChannelChange = now;
	}

	transmitAvailableBytes();
}
