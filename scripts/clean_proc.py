import os
import sys
import subprocess

def main():
    if sys.platform == "win32":
        cmd = 'powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like \'*sfl/fed_*\' -or $_.CommandLine -like \'*sfl/net/local_relay*\' } | Select-Object -ExpandProperty ProcessId"'
        try:
            out = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL)
            my_pid = os.getpid()
            for line in out.splitlines():
                line = line.strip()
                if line.isdigit() and int(line) != my_pid:
                    subprocess.run(["taskkill", "/F", "/PID", line], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

if __name__ == "__main__":
    main()
