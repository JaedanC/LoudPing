from __future__ import annotations
from enum import Enum
from playsound import playsound
from io import StringIO
from typing import List
import os
import re
import sys
import threading
import time


def get_resource(relative_path: str):
    if getattr(sys, 'frozen', False):
        base_path = os.path.dirname(sys.executable)
    elif __file__:
        base_path = os.path.dirname(__file__)
    return os.path.join(base_path, relative_path)


PUNCH_KICK = get_resource(os.path.join("wav", "punch_kick.wav"))


class Ping:
    class Stats:
        def __init__(self, ping_result):
            final_stats_regex = re.compile(r"    Packets: Sent = (\d+), Received = (\d+), Lost = (\d+) \((\d+)% loss\),")
            final_time_regex = re.compile(r"    Minimum = (\d+)ms, Maximum = (\d+)ms, Average = (\d+)ms")
            self.packets_sent = None
            self.packets_received = None
            self.packets_lost = None
            self.packets_lost_percent = None
            self.trip_time_min = None
            self.trip_time_max = None
            self.trip_time_avg = None

            for line in ping_result.split("\n"):
                line_match = final_stats_regex.match(line)
                if line_match is not None:
                    self.packets_sent = line_match.group(1)
                    self.packets_received = line_match.group(2)
                    self.packets_lost = line_match.group(3)
                    self.packets_lost_percent = line_match.group(4)
                
                line_match = final_time_regex.match(line)
                if line_match is not None:
                    self.trip_time_min = line_match.group(1)
                    self.trip_time_max = line_match.group(2)
                    self.trip_time_avg = line_match.group(3)

            assert self.packets_sent is not None
            assert self.packets_received is not None
            assert self.packets_lost is not None
            assert self.packets_lost_percent is not None
    
    class ReplyType(Enum):
        Success = 0
        RequestTimedOut = 1
        DestinationHostUnreachable = 2
        DestinationNetUnreachable = 3
        GeneralFailure = 4
    
    class Reply:
        def __init__(self, line: str, reply_type: Ping.ReplyType):
            self.line = line
            self.reply_type = reply_type
            self.ip = None
            self.bytes = None
            self.time = None
            self.ttl = None
            success_regex = re.compile(r"Reply from (.*): bytes=(\d+) time=(\d+)ms TTL=(\d+)")
            if self.reply_type is Ping.ReplyType.Success:
                success_match = re.match(success_regex, line)
                assert success_match is not None
                self.ip = success_match.group(1)
                self.bytes = int(success_match.group(2))
                self.time = int(success_match.group(3))
                self.ttl = int(success_match.group(4))
            
            unreachable_regex = re.compile(r"Reply from (.*): Destination host unreachable.")
            if self.reply_type is Ping.ReplyType.DestinationHostUnreachable:
                unreachable_match = re.match(unreachable_regex, line)
                assert unreachable_match is not None
                self.ip = unreachable_match.group(1)

    def __init__(self, ping_result: str):
        ip_regex = re.compile(r"Pinging (?:(.*?) )with 32 bytes of data")
        for line in ping_result.split("\n"):
            line_match = ip_regex.match(line)
            if line_match is not None:
                self.ip = line_match.group(1)
        assert self.ip is not None
                
        self.ping_result = ping_result
        self.ip = None
        self.pings: List[Ping.Reply] = []
        self.stats = Ping.Stats(ping_result)

        for line in ping_result.split("\n"):
            reply = None
            if line.endswith("Destination host unreachable."):
                reply = Ping.Reply(line, Ping.ReplyType.DestinationHostUnreachable)
            elif line.endswith("Destination net unreachable."):
                reply = Ping.Reply(line, Ping.ReplyType.DestinationNetUnreachable)
            elif line.startswith("Request timed out."):
                reply = Ping.Reply(line, Ping.ReplyType.RequestTimedOut)
            elif line.startswith("General failure."):
                reply = Ping.Reply(line, Ping.ReplyType.GeneralFailure)
            elif line.startswith("Reply from"):
                reply = Ping.Reply(line, Ping.ReplyType.Success)
            
            if reply is not None:
                self.pings.append(reply)

    def __repr__(self):
        output = StringIO()
        output.write(f"Ping({self.ip})\n")
        output.write("  Stats({}/{}. {}% lost. Min = {}ms, Max = {}ms, Avg = {}ms)\n".format(
            self.stats.packets_received,
            self.stats.packets_sent,
            self.stats.packets_lost,
            self.stats.trip_time_min,
            self.stats.trip_time_max,
            self.stats.trip_time_avg,
        ))
        for ping in self.pings:
            if ping.reply_type is Ping.ReplyType.Success:
                output.write(f"    Reply(Success, time={ping.time}ms, {ping.line})\n")
            if ping.reply_type is Ping.ReplyType.DestinationHostUnreachable:
                output.write(f"    Reply(DestinationHostUnreachable, {ping.line})\n")
            if ping.reply_type is Ping.ReplyType.DestinationNetUnreachable:
                output.write(f"    Reply(DestinationNetUnreachable, {ping.line})\n")
            if ping.reply_type is Ping.ReplyType.RequestTimedOut:
                output.write(f"    Reply(RequestTimedOut, {ping.line})\n")
            if ping.reply_type is Ping.ReplyType.GeneralFailure:
                output.write(f"    Reply(GeneralFailure, {ping.line})\n")

        return output.getvalue()


def do_ping(ip: str, atttempts: int = 4, _bytes: int =32):
    return Ping(os.popen(f"ping -n {atttempts} -l {_bytes} {ip}").read())


def play(sound: str):
    x = threading.Thread(
        target=lambda s: playsound(s, True),
        args=(sound,)
    )
    x.start()


def main():
    if len(sys.argv) < 2:
        print("Usage: lping <ip>")
        return
    
    ip = sys.argv[1]

    play_sound_after_x_fails = 2
    if len(sys.argv) >= 3:
        play_sound_after_x_fails = int(sys.argv[2])

    failed_in_a_row = 0
    success_times = []

    print()
    print(f"Pinging {ip} with 32 bytes of data:")
    packets = 0
    successes = 0
    try:
        while True:
            time.sleep(1)
            packets += 1
            result = do_ping(ip, atttempts=1)
            reply = result.pings[0]
            print(reply.line)

            if reply.time is not None:
                success_times.append(reply.time)
                
            if reply.reply_type is Ping.ReplyType.Success:
                successes += 1
                failed_in_a_row = 0
            else:
                failed_in_a_row += 1
                if failed_in_a_row >= play_sound_after_x_fails:
                    play(PUNCH_KICK)

    except KeyboardInterrupt:
        print()
    
    if packets > 0:
        print(f"Ping statistics for {ip}:")
        print("    Packets: Sent = {}, Received = {}, Lost = {} ({:.0f}% loss),".format(
            packets,
            successes,
            packets - successes,
            100 - (successes/packets) * 100
        ))
        if successes > 0:
            print(f"Approximate round trip times in milli-seconds:")
            print("    Minimum = {:.0f}ms, Maximum = {:.0f}ms, Average = {:.0f}ms".format(
                min(success_times),
                max(success_times),
                sum(success_times)/len(success_times)
            ))

              
if __name__ == "__main__":
    main()
