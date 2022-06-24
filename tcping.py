import argparse
import array
import random
import struct
import sys
import socket
from threading import current_thread
import time
from time import sleep
import signal
import sys
import platform
import select
from texttable import Texttable


if platform.system() != 'Linux':
    print('TCPing is only available on *nix-based systems')
    sys.exit(1)


class Stat:
    """
    Use this class as a container for tcping statistics.
    """

    def __init__(self) -> None:
        self.time_deltas = []

        self.min_t = 0
        self.max_t = 0
        self.avg_t = 0

        self.send = 0
        self.recv = 0

    def get_avg_time(self) -> int:
        if self.recv == 0:
            return -1
        return round(sum(self.time_deltas) / self.recv)

    def get_packet_loss(self) -> str:
        if self.send != 0:
            return int(100 * (self.send - self.recv) / self.send)
        return 0

    def add_delta(self, delta) -> None:
        self.time_deltas.append(delta)

    def max_delta(self) -> None:
        if len(self.time_deltas) != 0:
            return max(self.time_deltas)
        return -1

    def min_delta(self) -> None:
        if len(self.time_deltas) != 0:
            return min(self.time_deltas)
        return -1

    def print(self) -> None:
        print("\n")
        table = Texttable(max_width=150)
        fst_row = ['Avg', 'Min', 'Max', 'Sent', 'Recieved', 'Packet loss']

        left_part = list(map(lambda x: str(x) + 'ms', [self.get_avg_time(),
                         self.min_delta(), self.max_delta()]))
        right_part = [self.send, self.recv, str(self.get_packet_loss()) + '%']
        sec_row = left_part + right_part

        table.add_rows([fst_row, sec_row])
        print(table.draw())


stat = Stat()
wd_mode = False


def sigint_handler(signal, frame):
    stat.print()
    sys.exit(0)


def is_positive_num(arg):
    if not ((type(arg) is int or type(arg) == float) and arg > 0):
        print('You can only use positive numbers ' +
              'for port, count, interval and timeout')
        sys.exit(2)


def validate_port(port):
    if not (port >= 1 and port < 65535):
        print('Port number must be in range from 1 to 65635')
        sys.exit(3)


def new_socket(timeout):
    """
    Creates new raw socket with injectable TCP layer,
    so we can create the TCP packet in our own.
    """

    try:
        soc = socket.socket(
            socket.AF_INET,
            socket.SOCK_RAW,
            socket.IPPROTO_TCP)
        soc.settimeout(timeout)
    except socket.error as err:
        print('Unable to create raw socket due to error: ', err)
        sys.exit(4)
    return soc


def get_response(
        soc,
        syn_packet,
        dst_ip,
        port,
        seq_num,
        stat,
        wd_mode,
        poll):
    """
    Tries to get a SYN-ACK response to our SYN packet.
    """

    init_time = time.time()
   
    soc.sendto(syn_packet, (dst_ip, port))
    stat.send += 1
    
    while True:
        listFdAndEvent = poll.poll(soc.gettimeout() * 1000)
        if not listFdAndEvent:
            if wd_mode:
                print(f"Timeout {dst_ip}")
                with open(f'{dst_ip}.txt', 'w') as fh:
                    fh.write("0")
                return
            print(f'Unable to get a response from target host: {dst_ip}:[{port}]')
            return
        
        got_fd = listFdAndEvent[0][0]
        if got_fd == soc.fileno():
            data = soc.recv(2048)

            res = struct.unpack('!BBBBIIBB', data[20:34])

            ack_num = res[5]
            ack_flag =  res[7] == 18

            if seq_num + 1 == ack_num and ack_flag:
                delta = round((time.time() - init_time) * 1000)

                if wd_mode:
                    print(f"Get response {dst_ip}")
                    with open(f'{dst_ip}.txt', 'w') as fh:
                        fh.write("1")
                    return

                print(
                    f'OK! Got response from {dst_ip}:[{port}]' +
                    f' : seq = {seq_num}, time = {delta}ms')
                stat.recv += 1
                stat.add_delta(delta)
                return

def get_dst_ip(host):
    """
    Returns IP address for domain name with validation.
    """
    try:
        host_ip = socket.gethostbyname(host)
    except socket.error:
        print('Can\'t get IP address for this domain name')
        sys.exit(5)
    return host_ip


def get_src_ip():
    """
    Allows to get an actual src_ip.
    """
    soc = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    soc.connect(('1.1.1.1', 53))

    src_ip = soc.getsockname()[0]
    soc.close()
    return src_ip


def get_avail_port(soc):
    while (True):
        port = random.randint(49152, 65535)
        try:
            soc.bind(('0.0.0.0', port))
        except socket.error:
            continue
        else:
            return port


def get_checksum(msg):
    res = 0
    if len(msg) % 2 != 0:
        msg += b'\0'
    res = sum(array.array('H', msg))

    res = (res >> 16) + (res & 0xffff)
    res += res >> 16

    return (~res) & 0xffff


def form_packet(src_ip, src_port, dst_ip, dst_port, seq_num, flag):
    """
    This func is responsible for creation TCP SUN packet
    with checksum for pseudo header.
    """
    tcp_header = struct.pack(
        '!HHIIBBH',
        src_port,
        dst_port,
        seq_num,
        0,              # Acknowledgement

        80,             # According to RFC 793, we have 3 main
                        # fields in this part of packet: DataOff (4 bits),
                        # Reserved (6 bits, must be zero) and Flags (6 bits),
                        # So, we have 6+6+4 = 16 bits (2 bytes) and in case of
        flag,           # SYN packet we will get 01010000 | 00000010 = 80 | 2

        2048,           # Window Size
    )

    pshdr = struct.pack(
        '!4s4sHH',
        socket.inet_aton(src_ip),
        socket.inet_aton(dst_ip),
        socket.IPPROTO_TCP,
        len(tcp_header) + 4
    )

    checksum = get_checksum(pshdr + tcp_header)
    syn_packet = tcp_header + struct.pack('HH', checksum, 0)

    return syn_packet


def start_tcping_session(host, port, count, timeout, interval, wd_mode):
    """
    Initiates new tcping session, in which we will be sending
    TCP SYN packets and trying to recieve TCP ACK.
    """
    global stat
    stat = Stat()

    for arg in [port, count, timeout, interval]:
        is_positive_num(arg)
    validate_port(port)

    soc = new_socket(timeout)

    poll = select.poll()
    poll.register(soc, select.POLLIN)

    src_ip = get_src_ip()
    dst_ip = get_dst_ip(host)

    src_port = get_avail_port(soc)

    for _ in range(0, count):
        if wd_mode and current_thread().stopped():
            print(f'Stopped daemon responsible for {host}')
            break

        seq_num = random.randint(0, 1234567)

        syn_packet = form_packet(src_ip, src_port, dst_ip, port, seq_num, 2)

        get_response(
            soc,
            syn_packet,
            dst_ip,
            port,
            seq_num,
            stat,
            wd_mode, 
            poll)
        sleep(interval)

    soc.close()
    if not wd_mode:
        stat.print()


def parse_args(args):
    """
    Parses command line options an arguments.
    """
    parser = argparse.ArgumentParser(
        description='TCPing tool allows you to ping ' +
        'hosts without establishing connection')
    parser.add_argument(
        'host',
        type=str,
        help='Host which you\'d like to ping')
    parser.add_argument(
        '-p',
        '--port',
        type=int,
        default=80,
        help='Target port')
    parser.add_argument('-t', '--timeout',
                        type=float, default=0.5, help='Timeout (in seconds)')
    parser.add_argument(
        '-c',
        '--count',
        type=int,
        default=sys.maxsize,
        help='Number of connections counts (default = infinity)')
    parser.add_argument('-i', '--interval', type=float,
                        default=0.5, help='Interval between connections')

    return parser.parse_args(args)


def main(host, port, count, timeout, interval):
    """
    Tcping tool allows you to ping hosts by sending SYN TCP packet and
    recieving ACK TCP packet from other side.
    So, it doesn't need to establish TCP connection for pinging.
    """
    start_tcping_session(host, port, count, timeout, interval, wd_mode)


if __name__ == '__main__':
    signal.signal(signal.SIGINT, sigint_handler)
    args = parse_args(sys.argv[1:])
    main(args.host, args.port, args.count, args.timeout, args.interval)
