import gzip
from pathlib import Path
import struct
import tempfile
import unittest
from vgm2syx import parse, convert, wire_record, export, identity


def vgm(commands):
    header=bytearray(64);header[:4]=b'Vgm ';struct.pack_into('<I',header,8,0x150)
    return bytes(header)+commands


def note(chip=0):
    command=0x54 if chip==0 else 0xa4
    return b''.join(bytes([command,a,v]) for a,v in [(0x20,7),(0x80,31),(0x60,10),(0x40,1),(8,8)])


class ConversionTests(unittest.TestCase):
    def test_all_ratios_and_detunes(self):
        for ratio in range(64):
            for dt in range(8):
                raw=[0,7,15]+[(dt<<4)|(ratio>>2)]*4+[20]*4+[31]*4+[0]*4+[(ratio&3)<<6]*4+[0]*4
                v=convert(raw,'TEST')
                for op in range(4):
                    from vgm2syx import RATIOS
                    self.assertEqual(RATIOS[v[op*13+11]],ratio)
                    self.assertEqual(v[op*13+12],3+dt if dt<4 else 7-dt)
                    self.assertEqual(v[op*13+3],1)
                self.assertEqual(len(wire_record(v)),128)

    def test_dual_chip_waits_blocks(self):
        events=list(parse(vgm(b'\x67\x66\x00\x03\0\0\0abc'+note()+b'\x61\x44\xac'+note(1)+b'\x66'),'test'))
        self.assertEqual([e['chip'] for e in events],[0,1])
        self.assertEqual(events[1]['seconds'],1)

    def test_truncation_and_invalid_command(self):
        for command in (b'\x54\x08',b'\x61',b'\x67\x66\0\xff\xff\xff\x7f',b'\x01',note()):
            with self.assertRaises(ValueError):list(parse(vgm(command),'test'))

    def test_volume_grouping(self):
        event=list(parse(vgm(note()+b'\x66'),'test'))[0]
        other={**event,'raw':event['raw'].copy()};other['raw'][7]+=4
        self.assertEqual(identity(event),identity(other))
        self.assertNotEqual(identity(event,True),identity(other,True))

    def test_gzip_bank_and_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'test.vgz';path.write_bytes(gzip.compress(vgm(note()+b'\x66')))
            output=root/'result';self.assertEqual(export([path],output),1)
            bank=(output/'bank_001.syx').read_bytes()
            self.assertEqual(len(bank),4104)
            self.assertEqual(sum(bank[6:-1])&127,0)
            self.assertTrue(all(x<128 for x in bank[1:-1]))
            with self.assertRaises(ValueError):export([path],output)

if __name__=='__main__':unittest.main()
