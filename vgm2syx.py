#!/usr/bin/env python3
"""Extract YM2151 voices from VGM/VGZ into native TX81Z SysEx banks."""
import argparse
import collections
import csv
import gzip
import hashlib
import json
from pathlib import Path
import struct
import sys

CARRIERS = ((3,), (3,), (3,), (3,), (2, 3), (1, 2, 3), (1, 2, 3), (0, 1, 2, 3))
RATIOS = (0,1,2,3,4,5,6,7,8,9,12,10,11,16,13,14,20,15,17,24,18,19,28,21,22,32,25,23,36,26,29,40,27,30,44,33,48,31,34,37,52,35,56,41,38,60,45,39,42,49,46,43,53,50,47,57,54,51,61,58,55,62,59,63)
LOW_TL = (127,122,118,114,110,107,104,102,100,98,96,94,92,90,88,86,85,84,82,81)

def convert(b, name):
    """Equivalent to masanaohayashi/TX81Z Import/MdxVoice.h, without its runtime dependency."""
    v = [0]*110
    v[52], v[53], v[62], v[64] = b[1]&7, (b[1]>>3)&7, 24, 2
    v[77:87] = name.ljust(10).encode('ascii')
    for op in range(4):
        i = op*13
        v[i:i+5] = [b[11+op]&31, b[15+op]&31, b[19+op]&31, max(1,b[23+op]&15), 15-(b[23+op]>>4)]
        v[i+6], v[i+8] = b[11+op]>>6, b[15+op]>>7
        v[i+11] = RATIOS.index(((b[3+op]&15)<<2)|(b[19+op]>>6))
        dt = (b[3+op]>>4)&7
        v[i+12] = 3+dt if dt<4 else 7-dt
        offset = (0,0,0,0,8,13,13,16)[v[52]] if op in CARRIERS[v[52]] else 0
        v[i+10] = min(range(100), key=lambda ol: abs(min(127,(LOW_TL[ol] if ol<20 else 99-ol)+offset)-(b[7+op]&127)))
        if not b[2]&(1<<op):
            v[i] = v[i+10] = 0
    return v

def wire_record(v):
    p = [0]*78
    for op in range(4):
        i, j = op*10, op*13
        p[i:i+6] = v[j:j+6]
        p[i+6:i+10] = [(v[j+8]<<6)|(v[j+7]<<3)|v[j+9],v[j+10],v[j+11],(v[j+6]<<3)|v[j+12]]
    p[40] = (v[58]<<6)|(v[53]<<3)|v[52]
    p[41:45] = v[54:58]
    p[45:51] = [(v[60]<<4)|(v[61]<<2)|v[59],v[62],v[64],(v[70]<<4)|(v[63]<<3)|(v[68]<<2)|(v[69]<<1)|v[65],v[66],v[67]]
    p[51:67] = v[71:87]
    for op in range(4):
        i,j = 67+op*2,87+op*5
        p[i:i+2] = [(v[j+4]<<4)|(v[j]<<3)|v[j+1],(v[j+3]<<4)|v[j+2]]
    p[75:78] = v[107:110]
    w = [0]*128
    w[:67] = [x&127 for x in p[:67]]
    w[48] = (p[48]&13)|(2 if not p[48]&4 else 0)
    w[67:73] = [99]*3+[50]*3
    w[73:84] = [x&127 for x in p[67:78]]
    w[79] &= 15
    return bytes(w)

def parse(data, track):
    if len(data)<64 or data[:4]!=b'Vgm ':
        raise ValueError(f'{track}: VGMヘッダーが不正です')
    version = struct.unpack_from('<I',data,8)[0]
    offset = struct.unpack_from('<I',data,0x34)[0] if version>=0x150 else 0
    pos = 0x34+offset if offset else 0x40
    if pos<64 or pos>=len(data):
        raise ValueError(f'{track}: データ開始位置が不正です')
    regs = [bytearray(256),bytearray(256)]
    depths = [[0,0],[0,0]]
    waits = {0x62:735,0x63:882}
    time = 0
    def need(n):
        if pos+n>len(data):
            raise ValueError(f'{track}: 0x{pos:X}でコマンドが途切れています')
    while pos<len(data):
        c = data[pos]
        if c==0x66:
            return
        if c in (0x54,0xa4):
            need(3)
            chip = int(c==0xa4)
            a,val = data[pos+1:pos+3]
            r = regs[chip]; r[a] = val
            if a==0x19:
                depths[chip][int(bool(val&128))] = val&127
            if a==8 and val&120:
                ch,mask = val&7,(val>>3)&15
                ops = [[r[base+slot*8+ch] for base in (64,96,128,160,192,224)] for slot in range(4)]
                if any(mask&(1<<i) and op[2]&31 and op[1]&127<127 for i,op in enumerate(ops)):
                    b = [0,r[32+ch]&63,mask]+[ops[i][g] for g in range(6) for i in range(4)]
                    lfo = [r[24],*depths[chip],r[27]&3,r[15],r[56+ch]]
                    kc = r[40+ch]
                    yield dict(raw=b, lfo=lfo, track=track, chip=chip, channel=ch+1, seconds=time/44100,
                               pitch=(kc>>4)*12+((kc&15)//4)*3+(kc&3)+13+r[48+ch]/256)
            n=3
        elif c==0x67:
            need(7)
            if data[pos+1]!=0x66: raise ValueError(f'{track}: データブロックのマーカーが不正です')
            n=7+(struct.unpack_from('<I',data,pos+3)[0]&0x7fffffff)
        elif c==0x68:
            need(12)
            if data[pos+1]!=0x66: raise ValueError(f'{track}: PCM RAMマーカーが不正です')
            n=12
        elif c==0x61:
            need(3); time+=struct.unpack_from('<H',data,pos+1)[0]; n=3
        elif c in waits:
            time+=waits[c]; n=1
        elif c==0x64:
            need(4)
            if data[pos+1] not in waits: raise ValueError(f'{track}: 不正なwait override')
            waits[data[pos+1]]=struct.unpack_from('<H',data,pos+2)[0]; n=4
        elif 0x70<=c<=0x8f:
            time+=(c&15)+(c<0x80); n=1
        elif c in (0x90,0x91,0x92,0x93,0x94,0x95):
            n={0x90:5,0x91:5,0x92:6,0x93:11,0x94:2,0x95:5}[c]
        elif 0x30<=c<=0x3f or c in (0x4f,0x50): n=2
        elif 0x51<=c<=0x5f or 0xa0<=c<=0xbf: n=3
        elif 0xc0<=c<=0xdf: n=4
        elif 0xe0<=c<=0xff: n=5
        else: raise ValueError(f'{track}: 未対応コマンド0x{c:02X} (0x{pos:X})')
        need(n); pos+=n
    raise ValueError(f'{track}: 終端コマンドがありません')

def identity(event, keep_volume=False):
    b = event['raw'].copy(); b[0]=0
    if not keep_volume:
        carriers = [i for i in CARRIERS[b[1]&7] if b[2]&(1<<i)]
        floor = min((b[7+i]&127 for i in carriers),default=0)
        for i in carriers: b[7+i]=(b[7+i]&127)-floor
    lfo=event['lfo']
    active = (lfo[2] and lfo[5]>>4&7) or (lfo[1] and lfo[5]&3)
    return tuple(b)+tuple(lfo if active or event['channel']==8 and lfo[4]&128 else [0]*6)

def export(paths, output, prefix='V', channel=1, keep_volume=False):
    if output.exists() and any(output.iterdir()): raise ValueError(f'出力先が空ではありません: {output}')
    groups={}; inputs=[]
    for path in paths:
        with path.open('rb') as f:
            compressed=f.read(2)==b'\x1f\x8b'
        with (gzip.open(path,'rb') if compressed else path.open('rb')) as f:
            data=f.read(512*1024*1024+1)
        if len(data)>512*1024*1024: raise ValueError(f'{path}: サイズ上限512MiBを超えています')
        inputs.append(dict(path=str(path),sha256=hashlib.sha256(data).hexdigest()))
        for event in parse(data,str(path)):
            key=identity(event,keep_volume)
            g=groups.setdefault(key,dict(variants={},usage={}))
            exact=tuple(event['raw'])
            variant=g['variants'].setdefault(exact,dict(event=event,count=0)); variant['count']+=1
            use=g['usage'].setdefault((str(path),event['chip'],event['channel']),dict(count=0,first=event['seconds'],last=event['seconds'],pitch_min=event['pitch'],pitch_max=event['pitch']))
            use['count']+=1;use['last']=event['seconds'];use['pitch_min']=min(use['pitch_min'],event['pitch']);use['pitch_max']=max(use['pitch_max'],event['pitch'])
    if not groups: raise ValueError('YM2151の発音を抽出できませんでした。現在YM2151のみ対応です。')
    ordered=sorted(groups.values(),key=lambda g:-sum(v['count'] for v in g['variants'].values()))
    if len(ordered)>99999: raise ValueError('音色数が上限99999を超えています')
    output.mkdir(parents=True,exist_ok=True)
    records=[]; rows=[]; raw=[]
    for num,g in enumerate(ordered,1):
        event=max(g['variants'].values(),key=lambda v:v['count'])['event']
        name=f'{prefix}{num:03d}'
        if len(name)>10: raise ValueError('音色名が10文字を超えます')
        v=convert(event['raw'],name); records.append(wire_record(v));raw.append(event['raw'])
        warnings=[];lfo=event['lfo']
        if (lfo[2] and lfo[5]>>4&7) or (lfo[1] and lfo[5]&3): warnings.append('LFO変調は静的音色に未変換')
        if event['channel']==8 and lfo[4]&128: warnings.append('YM2151ノイズは未変換')
        usage=[dict(track=k[0],chip=k[1],channel=k[2],**u) for k,u in sorted(g['usage'].items())]
        rows.append(dict(name=name,bank=(num-1)//32+1,slot=(num-1)%32+1,source=event,volume_variants=len(g['variants']),warnings=warnings,usage=usage))
    init=convert([0,0,15]+[1]*4+[127]*4+[31]*4+[0]*4+[0]*4+[15]*4,'INIT VOICE')
    for start in range(0,len(records),32):
        bank=records[start:start+32]+[wire_record(init)]*(32-len(records[start:start+32]))
        payload=b''.join(bank)
        (output/f'bank_{start//32+1:03d}.syx').write_bytes(bytes([240,67,channel-1,4,32,0])+payload+bytes([(-sum(payload))&127,247]))
    for start in range(0,len(raw),256):
        voices=[bytes([i]+b[1:]) for i,b in enumerate(raw[start:start+256])]
        offsets=[38]+[20+2*i for i in range(9)]
        (output/f'source_{start//256+1:03d}.mdx').write_bytes(b'VGM FM voices\r\n\x1a\0'+b''.join(n.to_bytes(2,'big') for n in offsets)+b'\xf1\0'*9+b''.join(voices))
    (output/'voices.json').write_text(json.dumps(dict(format_version=1,inputs=inputs,voices=rows),ensure_ascii=False,indent=2)+'\n')
    with (output/'usage.tsv').open('w',newline='') as f:
        writer=csv.writer(f,delimiter='\t');writer.writerow(['voice','bank','slot','track','chip','channel','key_ons','first_seconds','last_seconds','estimated_pitch_min','estimated_pitch_max'])
        for row in rows:
            for u in row['usage']: writer.writerow([row['name'],row['bank'],row['slot'],u['track'],u['chip'],u['channel'],u['count'],round(u['first'],3),round(u['last'],3),round(u['pitch_min'],2),round(u['pitch_max'],2)])
    (output/'README.txt').write_text('TX81Z用 YM2151音色\n\nbank_*.syx: 32音色ずつのネイティブバンク。TX81Zソフトに読み込めます。\nバンク内の番号は1〜32、未使用スロットはINIT VOICEです。\nsource_*.mdx: 原音確認用の元音色。曲データは空です。256音色ずつ。\nusage.tsv: 曲、チップ(0/1)、チャンネル(1〜8)、発音回数と使用時刻。\nvoices.json: 元レジスタと全使用情報。\n\n変換は確認済みのTX81Z MDX変換と同じ計算です。\n共通キャリア音量の違いは既定で統合し、最も頻出する状態を採用。\n音色はキーオン時の状態。演奏中のパラメーター変化、曲の重ね合わせ、\nPCM、LFO変調、ノイズ、パンは再現しません。警告はvoices.jsonに記録。\n時刻はVGMを一度再生した範囲。ループは繰り返しません。\n推定音高はKC/KFからの値で、チップクロックによる補正は含みません。\n音色から楽器名や曲内の役割を自動判定する機能はありません。\n')
    return len(rows)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--version',action='version',version='vgm2syx 0.1.0')
    p.add_argument('inputs',nargs='+',type=Path,help='VGM/VGZファイル、またはフォルダ')
    p.add_argument('-o','--output',required=True,type=Path,help='空の出力フォルダ')
    p.add_argument('--prefix',default='V',help='ASCII音色名の接頭辞（最大5文字）')
    p.add_argument('--midi-channel',type=int,choices=range(1,17),default=1)
    p.add_argument('--keep-volume-variants',action='store_true')
    args=p.parse_args()
    if not args.prefix.isascii() or not args.prefix.isalnum() or len(args.prefix)>5: p.error('--prefixはASCII英数字1〜5文字です')
    paths=set()
    for path in args.inputs:
        if path.is_dir(): paths.update(f.resolve() for f in path.rglob('*') if f.is_file() and f.suffix.lower() in ('.vgm','.vgz'))
        else: paths.add(path.resolve())
    if not paths:p.error('VGM/VGZがありません')
    try: count=export(sorted(paths),args.output.resolve(),args.prefix,args.midi_channel,args.keep_volume_variants)
    except (ValueError,OSError,EOFError) as error:p.exit(1,f'エラー: {error}\n')
    print(f'{count}音色 / {(count+31)//32}バンク: {args.output.resolve()}')

if __name__=='__main__': main()
