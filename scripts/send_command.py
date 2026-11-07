#!/usr/bin/env python3
"""Send one MQTT command to the vacuum and print the decoded response.

Usage:
  export NARWAL_EMAIL=... NARWAL_PASSWORD=... NARWAL_REGION=us \
         NARWAL_PRODUCT_KEY=... NARWAL_DEVICE_ID=...
  python scripts/send_command.py config/get
  python scripts/send_command.py common/get_device_info --wait 20
  python scripts/send_command.py config/get --extra 0801   # append field 1 = 1

The vacuum is woken first (active_robot_publish) because it ignores
commands while in deep sleep.  Use --no-wake to skip that.
"""

from __future__ import annotations

import argparse
import re
import sys
import time

from _common import (
    NarwalMQTT,
    auth_payload,
    cloud_login,
    get_config,
    parse_protobuf_fields,
    pb_string,
    pb_varint,
)


def active_robot_payload(user_uuid: str) -> bytes:
    """Wake/keepalive payload, same as the integration's notify_active()."""
    keepalive = pb_varint(1, 2000) + pb_varint(2, 2000) + pb_varint(3, 2000)
    extra = pb_string(1, keepalive) + pb_varint(8, 0) + pb_varint(2, 60000) + pb_varint(3, 0)
    return auth_payload(user_uuid) + extra


def _try_nested(data: bytes) -> dict[int, list] | None:
    """Return parsed fields if `data` looks like a complete protobuf message."""
    if not data:
        return None
    try:
        fields = parse_protobuf_fields(data)
    except Exception:
        return None
    if not fields or any(n == 0 or n > 536870911 for n in fields):
        return None
    # Re-check the parser consumed sensible values (no truncated blobs).
    for vals in fields.values():
        for v in vals:
            if isinstance(v, bytes) and len(v) > len(data):
                return None
    return fields


def dump(fields: dict[int, list], indent: int = 0, depth: int = 0) -> None:
    pad = "  " * indent
    for num in sorted(fields):
        for val in fields[num]:
            if isinstance(val, int):
                print(f"{pad}{num}: {val}")
                continue
            text = None
            try:
                decoded = val.decode("utf-8")
                if decoded and decoded.isprintable():
                    text = decoded
            except UnicodeDecodeError:
                pass
            nested = _try_nested(val) if depth < 8 else None
            if text is not None and (nested is None or len(text) > 2):
                print(f'{pad}{num}: "{text}"')
            elif nested is not None:
                print(f"{pad}{num}: {{")
                dump(nested, indent + 1, depth + 1)
                print(f"{pad}}}")
            else:
                print(f"{pad}{num}: <{len(val)} bytes> {val.hex()}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a Narwal MQTT command")
    parser.add_argument("topic", nargs="?", default="config/get",
                        help="Command topic suffix (default: config/get)")
    parser.add_argument("--wait", type=float, default=15.0,
                        help="Seconds to wait for the response (default: 15)")
    parser.add_argument("--extra", default="",
                        help="Hex bytes appended after the auth frame (request body), e.g. 0801")
    parser.add_argument("--no-wake", action="store_true",
                        help="Don't send active_robot_publish first")
    args = parser.parse_args()

    if "/" not in args.topic:
        print(f"WARNING: '{args.topic}' has no category prefix — did you mean "
              f"'common/{args.topic}'? (e.g. common/reboot, config/get)")

    cfg = get_config()
    if not re.fullmatch(r"[0-9a-fA-F]{32}", cfg["device_id"]):
        print("WARNING: NARWAL_DEVICE_ID should be the 32-char hex MQTT device "
              "name (HA config entry 'device_name'), not the cloud device ID.")
    user_uuid, token = cloud_login(cfg)

    mq = NarwalMQTT(cfg, user_uuid, token)
    mq.connect()
    print(f"Connected to {cfg['mqtt_host']} | base topic {mq.base}")

    try:
        if not args.no_wake:
            mq.client.publish(
                f"{mq.base}/common/active_robot_publish",
                active_robot_payload(user_uuid), qos=1,
                properties=mq.make_props("common/active_robot_publish"),
            )
            print("Sent wake, waiting 2s...")
            time.sleep(2)

        print(f"Sending {args.topic} ...")
        payload = auth_payload(user_uuid) + bytes.fromhex(args.extra)
        if args.extra:
            print(f"Request body (after auth frame): {args.extra}")
        resp = mq.send_command(args.topic, payload, wait=args.wait)
    finally:
        mq.disconnect()

    if resp is None:
        print(f"No response within {args.wait:.0f}s (vacuum asleep or command unsupported).")
        sys.exit(1)

    print(f"\nResponse: {len(resp)} bytes")
    print(f"Hex: {resp.hex()}\n")
    # Skip the 0x01 Narwal frame marker, same as the integration does.
    body = resp[1:] if resp[:1] == b"\x01" else resp
    fields = _try_nested(body)
    if fields is None:
        print("(could not decode as protobuf)")
    else:
        print("Decoded fields:")
        dump(fields, indent=1)


if __name__ == "__main__":
    main()
