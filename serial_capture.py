import argparse
import struct
import sys
import time

import serial


BAUD_RATE = 921600
MAGIC = b"\xAA\xBB\xCC\xDD"
READ_SIZE = 4096
MAX_PACKET_SIZE = 0xFFFF

PCAP_GLOBAL_HEADER = struct.pack(
    "<IHHIIII",
    0xA1B2C3D4,
    2,
    4,
    0,
    0,
    MAX_PACKET_SIZE,
    105,
)


def write_packet(pcap_file, packet):
    timestamp_us = time.time_ns() // 1000
    timestamp_seconds, timestamp_fraction = divmod(timestamp_us, 1_000_000)
    packet_header = struct.pack(
        "<IIII",
        timestamp_seconds,
        timestamp_fraction,
        len(packet),
        len(packet),
    )
    pcap_file.write(packet_header)
    pcap_file.write(packet)
    pcap_file.flush()


def capture(port):
    buffer = bytearray()

    with open("live_stream.pcap", "wb") as pcap_file:
        pcap_file.write(PCAP_GLOBAL_HEADER)
        pcap_file.flush()

        with serial.Serial(port, BAUD_RATE, timeout=0.1) as connection:
            print(
                f"Capturing from {port} at {BAUD_RATE} baud to live_stream.pcap; "
                "press Ctrl+C to stop.",
                file=sys.stderr,
            )
            while True:
                bytes_waiting = connection.in_waiting
                read_size = min(bytes_waiting, READ_SIZE) if bytes_waiting else 1
                chunk = connection.read(read_size)
                if chunk:
                    buffer.extend(chunk)

                while True:
                    magic_index = buffer.find(MAGIC)
                    if magic_index < 0:
                        if len(buffer) > len(MAGIC) - 1:
                            del buffer[: -(len(MAGIC) - 1)]
                        break
                    if magic_index:
                        del buffer[:magic_index]
                    if len(buffer) < len(MAGIC) + 2:
                        break

                    packet_length = int.from_bytes(buffer[4:6], "little")
                    if not 0 < packet_length <= MAX_PACKET_SIZE:
                        del buffer[0]
                        continue

                    frame_end = len(MAGIC) + 2 + packet_length
                    if len(buffer) < frame_end:
                        break

                    packet = bytes(buffer[len(MAGIC) + 2:frame_end])
                    del buffer[:frame_end]
                    write_packet(pcap_file, packet)


def main():
    parser = argparse.ArgumentParser(
        description="Capture framed ESP32 Wi-Fi packets into live_stream.pcap."
    )
    parser.add_argument("port", help="serial port, for example COM3")
    args = parser.parse_args()

    try:
        capture(args.port)
    except KeyboardInterrupt:
        print("Capture stopped.", file=sys.stderr)
    except serial.SerialException as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()