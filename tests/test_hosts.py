#!/usr/bin/python
# coding=utf-8

import sys
sys.path.insert(0, '../')
import unittest
from lib.hosts import Host, Hosts
from lib.process import PortPool
import socket
import os
import tempfile
import time
import stat
import operator


class HostsTestCase(unittest.TestCase):
    def setUp(self):
        PortPool().change_range()
        self.path = tempfile.mktemp(prefix="test-storage")
        self.hosts = Hosts()
        self.hosts.set_settings(self.path, os.environ.get('MONGOBIN', ""))

    def remove_path(self, path):
        onerror = lambda func, filepath, exc_info: (os.chmod(filepath, stat.S_IWUSR), func(filepath))
        if os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                time.sleep(2)
                onerror(os.remove, path, None)

    def tearDown(self):
        self.hosts.cleanup()
        self.hosts._storage.disconnect()
        self.remove_path(self.path)

    def test_singleton(self):
        self.assertEqual(id(self.hosts), id(Hosts()))

    def test_set_settings(self):
        path = tempfile.mktemp(prefix="test-set-settings-")
        self.hosts.set_settings(path)
        self.assertEqual(path, self.hosts.pids_file)
        self.remove_path(path)

    def test_bool(self):
        self.assertEqual(False, bool(self.hosts))
        self.hosts.create('mongod', {}, autostart=False)
        self.assertTrue(True, bool(self.hosts))

    def test_operations(self):
        host_id = self.hosts.create('mongod', {}, autostart=False)
        self.assertTrue(len(self.hosts) == 1)
        self.assertTrue(host_id in self.hosts)
        host_id2, host2 = 'host-id2', Host('mongod', {}, None)
        host2.start(20)
        host2_pid = host2.info()['procInfo']['pid']
        self.hosts[host_id2] = host2
        self.assertTrue(self.hosts[host_id2]['procInfo']['pid'] == host2_pid)
        self.assertTrue(host_id2 in self.hosts)
        for h_id in self.hosts:
            self.assertTrue(h_id in (host_id, host_id2))

        operator.delitem(self.hosts, host_id2)
        self.assertFalse(host_id2 in self.hosts)
        host2.stop(), host2.cleanup()

    def test_cleanup(self):
        self.hosts.create('mongod', {}, autostart=False)
        self.hosts.create('mongod', {}, autostart=True)
        self.assertTrue(len(self.hosts) == 2)
        self.hosts.cleanup()
        self.assertTrue(len(self.hosts) == 0)

    def test_new_host(self):
        self.assertTrue(len(self.hosts) == 0)
        host_id = self.hosts.create('mongod', {}, autostart=False)
        info = self.hosts.info(host_id)
        self.assertTrue(len(self.hosts) == 1)
        self.assertEqual(info['procInfo']['pid'], None)
        host_id2 = self.hosts.create('mongod', {}, autostart=True)
        info = self.hosts.info(host_id2)
        self.assertTrue(info['procInfo']['pid'] > 0)

        self.assertRaises(OSError, self.hosts.create, 'fake_process_', {})

    def test_hdel(self):
        self.assertEqual(len(self.hosts), 0)
        h_id = self.hosts.create('mongod', {}, autostart=True)
        self.assertEqual(len(self.hosts), 1)
        h_info = self.hosts.info(h_id)['procInfo']
        self.assertTrue(os.path.exists(h_info['params']['dbpath']))
        self.assertTrue(os.path.exists(h_info['optfile']))
        self.hosts.remove(h_id)
        self.assertEqual(len(self.hosts), 0)  # check length
        # check cleanup
        self.assertFalse(os.path.exists(h_info['params']['dbpath']))
        self.assertFalse(os.path.exists(h_info['optfile']))

    def test_hcommand(self):
        h_id = self.hosts.create('mongod', {}, autostart=False)
        self.assertTrue(self.hosts.command(h_id, 'start'))
        self.assertTrue(self.hosts.command(h_id, 'stop'))
        self.assertTrue(self.hosts.command(h_id, 'start'))
        self.assertTrue(self.hosts.command(h_id, 'restart'))
        self.assertRaises(ValueError, self.hosts.command, h_id, 'fake')

    def test_hinfo(self):
        h_id = self.hosts.create('mongod', {}, autostart=False)
        info = self.hosts.info(h_id)
        self.assertEqual(info['id'], h_id)
        self.assertEqual(info['procInfo']['pid'], None)
        self.assertEqual(info['statuses'], {})
        self.assertEqual(info['serverInfo'], {})

    def test_id_by_hostname(self):
        h_id = self.hosts.create('mongod', {}, autostart=True)
        h_uri = self.hosts.info(h_id)['uri']
        h2_id = self.hosts.create('mongod', {}, autostart=True)
        h2_uri = self.hosts.info(h2_id)['uri']
        self.assertTrue(self.hosts.id_by_hostname(h_uri) == h_id)
        self.assertTrue(self.hosts.id_by_hostname(h2_uri) == h2_id)

    def test_hostname(self):
        h_id = self.hosts.create('mongod', {}, autostart=True)
        h_uri = self.hosts.info(h_id)['uri']
        self.assertEqual(self.hosts.hostname(h_id), h_uri)


class HostTestCase(unittest.TestCase):
    def setUp(self):
        PortPool().change_range()
        mongod = os.path.join(os.environ.get('MONGOBIN', ''), 'mongod')
        self.host = Host(mongod, {}, None)

    def tearDown(self):
        if hasattr(self, 'host'):
            self.host.stop()
            self.host.cleanup()

    def test_host(self):
        self.assertTrue(isinstance(self.host, Host))

    def test_info(self):
        self.host.start(10)
        info = self.host.info()
        for item in ("uri", "statuses", "serverInfo", "procInfo"):
            self.assertTrue(item in info)

        fd_log, log_path = tempfile.mkstemp()
        db_path = tempfile.mkdtemp()
        params = {'logPath': log_path, 'dbpath': db_path}
        host2 = Host('mongod', params, None)
        host2.start(10)
        info2 = host2.info()
        for param, value in params.items():
            self.assertTrue(info2['procInfo']['params'].get(param, value) == value)
        host2.stop()
        host2.cleanup()

    def test_start(self):
        self.assertTrue(self.host.info()['procInfo']['pid'] is None)
        self.assertTrue(self.host.start(10))
        self.assertTrue(self.host.info()['procInfo']['pid'] > 0)

        fake_host = Host('fake_proc_', {}, None)
        self.assertFalse(fake_host.start(5))
        fake_host.cleanup()

    def test_stop(self):
        self.assertTrue(self.host.start(60))
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        host = self.host.hostname.split(':')[0]
        s.connect((host, self.host.cfg['port']))
        self.assertTrue(self.host.stop())
        self.assertRaises(socket.error, s.connect, (host, self.host.cfg['port']))

    def test_restart(self):
        self.assertTrue(self.host.start(20))
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        host = self.host.hostname.split(':')[0]
        s.connect((host, self.host.cfg['port']))
        s.shutdown(0)
        s.close()
        self.assertTrue(self.host.restart(20))
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((host, self.host.cfg['port']))
        s.shutdown(0)
        s.close()

    def test_cleanup(self):
        self.host.start(80)
        self.assertTrue(os.path.exists(self.host.cfg['dbpath']))
        self.assertTrue(os.path.exists(self.host.config_path))
        self.host.stop()
        self.host.cleanup()
        self.assertFalse(os.path.exists(self.host.cfg['dbpath']))
        self.assertFalse(os.path.exists(self.host.config_path))


if __name__ == '__main__':
    unittest.main()
