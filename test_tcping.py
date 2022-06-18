import os
import socket
import unittest
import tcping
import sys


class TestTCPing(unittest.TestCase):

    def test_norm_stats(self):
        stat = tcping.Stat()
        stat.send = 10
        stat.recv = 5
        stat.time_deltas = [10, 20, 30, 40, 50]

        self.assertAlmostEqual(150 / 5, stat.get_avg_time())
        self.assertAlmostEqual(50, stat.get_packet_loss())

        self.assertEqual(10, stat.min_delta())
        self.assertEqual(50, stat.max_delta())

    def test_incorrect_stats(self):
        stat = tcping.Stat()
        stat.send = 15
        stat.recv = 0

        self.assertEqual(-1, stat.min_delta())
        self.assertEqual(-1, stat.max_delta())
        self.assertEqual(-1, stat.get_avg_time())

    def test_dst_ip(self):
        expected = '77.88.8.8'
        real = tcping.get_dst_ip('dns.yandex')
        self.assertEqual(expected, real)

    def test_form_syn(self):
        src_ip = "172.22.90.211"
        src_port = 49155

        dst_ip = '178.248.233.33'
        dst_port = 80

        seq_num = 420

        expected = b'\xc0\x03\x00P\x00\x00\x01\xa4\x00\x00\x00\x00P\x02\x08\x00B\xe7\x00\x00'
        real = tcping.form_packet(
            src_ip, src_port, dst_ip, dst_port, seq_num, 2)

        self.assertEqual(expected, real)

    def test_new_socket(self):
        timeout = 2
        soc = tcping.new_socket(timeout)
        self.assertIsInstance(soc, socket.socket)
        soc.close()

    def test_parse_args(self):
        args = tcping.parse_args(['1.1.1.1', '-p', '53'])
        self.assertEqual(args.host, '1.1.1.1')
        self.assertEqual(args.port, 53)

    def test_is_positive_num(self):
        with self.assertRaises(SystemExit) as cm:
            tcping.is_positive_num(-512),
        self.assertEqual(cm.exception.code, 2)

    def test_validate_port(self):
        with self.assertRaises(SystemExit) as cm:
            tcping.validate_port(65539),
        self.assertEqual(cm.exception.code, 3)

    def test_get_checksum(self):
        pshdr = b'\xac\x1d\xd2\xac\xb2\xf8\xe9!\x00\x06\x00\x14'
        tcp_header = b'\xc0\x03\x00P\x00\x00\x01\xa4\x00\x00\x00\x00P\x02\x08\x00'

        expected = 1739
        real = tcping.get_checksum(pshdr + tcp_header)
        self.assertEqual(expected, real)

    def test_start_tcp_session(self):

        wd_mode = False

        with open("expected_output.txt", 'w') as exp_out:
            exp_out.write(
                """Unable to get a response from target host: 77.88.8.8:[50]


+------+------+------+------+----------+-------------+
| Avg  | Min  | Max  | Sent | Recieved | Packet loss |
+======+======+======+======+==========+=============+
| -1ms | -1ms | -1ms | 1    | 0        | 100%        |
+------+------+------+------+----------+-------------+""")

        with open("expected_output.txt", 'rb') as exp_out:
            exp_lines = exp_out.read()

        init_stdout = sys.stdout

        sys.stdout = open("real_output.txt", 'w')

        tcping.start_tcping_session("77.88.8.8", 50, 1, 0.5, 0.5, wd_mode)
        sys.stdout.close()

        sys.stdout = init_stdout
        with open("expected_output.txt", 'rb') as real_out:
            real_lines = real_out.read()

        os.remove("expected_output.txt")
        os.remove("real_output.txt")

        self.assertEqual(exp_lines, real_lines)


if __name__ == "__main__":
    unittest.main()
