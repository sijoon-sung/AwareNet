"""Task-local QEMU launcher and serial console (no host network changes)."""
import argparse
import hashlib
import json
from pathlib import Path
import select
import socket
import subprocess
import time

ROOT=Path(__file__).resolve().parents[2]
TOOLS=ROOT/'tmp/lab-tools'

def launch():
    state=json.loads((ROOT/'tmp/observability/current.json').read_text(encoding='utf-8'))
    runtime=Path(state['runtime'])
    iso=TOOLS/'downloads/alpine.iso'
    assert hashlib.sha256(iso.read_bytes()).hexdigest()==(TOOLS/'downloads/alpine.sha256').read_text().split()[0]
    cmd=[str(TOOLS/'qemu/qemu-system-x86_64.exe'),'-L','share','-accel','tcg','-m','1024','-smp','2',
         '-kernel','../alpine/boot/vmlinuz-virt','-initrd','../alpine/boot/initramfs-virt',
         '-append','console=ttyS0,115200 modules=loop,squashfs,sd-mod,virtio_net nomodeset',
         '-drive','file=../downloads/alpine.iso,media=cdrom,readonly=on','-nic','user,model=virtio-net-pci',
         '-display','none','-serial','tcp:127.0.0.1:15556,server=on,wait=off','-no-reboot']
    with (runtime/'qemu.log').open('wb') as log:
        proc=subprocess.Popen(cmd,cwd=TOOLS/'qemu',stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                              creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    state['pids']['qemu']=proc.pid
    (ROOT/'tmp/observability/current.json').write_text(json.dumps(state,indent=2),encoding='utf-8')
    (runtime/'vm-command.json').write_text(json.dumps(cmd,indent=2),encoding='utf-8')
    print(json.dumps({'qemu_pid':proc.pid}))

def console(command, seconds):
    state=json.loads((ROOT/'tmp/observability/current.json').read_text(encoding='utf-8'))
    with socket.create_connection(('127.0.0.1',15556),timeout=5) as sock:
        if command is not None:sock.sendall(command.encode()+b'\r')
        end=time.monotonic()+seconds
        with (Path(state['runtime'])/'serial.log').open('ab') as log:
            while time.monotonic()<end:
                ready,_,_=select.select([sock],[],[],min(1,max(0,end-time.monotonic())))
                if ready:
                    data=sock.recv(65536)
                    if not data:break
                    log.write(data);log.flush()
                    print(data.decode(errors='replace'),end='',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['launch','console'])
    p.add_argument('--command');p.add_argument('--seconds',type=float,default=8)
    a=p.parse_args()
    launch() if a.mode=='launch' else console(a.command,a.seconds)
