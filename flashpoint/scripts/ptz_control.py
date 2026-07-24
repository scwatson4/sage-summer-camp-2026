#!/usr/bin/env python3
"""PTZ camera-control starter for Waggle/Sage nodes (run ON the node, e.g. W0A4).

Prereq: your SSH key provisioned on the node (gateway auth already works for you;
'Permission denied (publickey)' at the node = ask your Sage contact to add scwatson).

On Waggle nodes, cameras live on the node's internal camera subnet (commonly
10.31.81.0/24) and speak vendor HTTP APIs and/or ONVIF. Typical stack:
  - Hanwha (XNV/PNM/PTZ '8081' etc.): SUNAPI  http://<cam>/stw-cgi/ptzcontrol.cgi
  - AXIS: VAPIX                       http://<cam>/axis-cgi/com/ptz.cgi
  - Mobotix (M16 thermal, pan-tilt head separate)
  - Almost everything: ONVIF (port 80/8899) -> `pip install onvif-zeep`
Credentials: ask the node admins (cameras are usually admin/<node-specific>);
NEVER guess-brute-force on shared infrastructure.

Steps:
  1) python3 ptz_control.py discover           # find live camera IPs
  2) python3 ptz_control.py onvif <ip> <user> <pass> --pan 0.5   # nudge right
  3) or use the curl one-liners printed by `examples`
"""
import socket, sys, time

SUBNET = "10.31.81."          # adjust if `ip -4 addr` on the node shows otherwise
PORTS = [80, 554, 8899]        # http / rtsp / onvif-alt

def discover():
    print(f"scanning {SUBNET}1-40 on ports {PORTS} ...")
    for host in range(1, 41):
        ip = SUBNET + str(host)
        open_ports = []
        for p in PORTS:
            s = socket.socket(); s.settimeout(0.25)
            try:
                s.connect((ip, p)); open_ports.append(p)
            except Exception:
                pass
            finally:
                s.close()
        if open_ports:
            print(f"  {ip}: open {open_ports}  <- likely a camera")
    print("Tip: `arp -a` and `ip neigh` on the node also reveal camera MACs (Hanwha=00:09:18, Axis=AC:CC:8E).")

def onvif_move(ip, user, pw, pan=0.0, tilt=0.0, zoom=0.0, secs=1.0):
    from onvif import ONVIFCamera          # pip install onvif-zeep
    cam = ONVIFCamera(ip, 80, user, pw)
    media = cam.create_media_service()
    ptz = cam.create_ptz_service()
    profile = media.GetProfiles()[0]
    req = ptz.create_type("ContinuousMove")
    req.ProfileToken = profile.token
    req.Velocity = {"PanTilt": {"x": pan, "y": tilt}, "Zoom": {"x": zoom}}
    ptz.ContinuousMove(req)
    time.sleep(secs)
    ptz.Stop({"ProfileToken": profile.token})
    print(f"moved pan={pan} tilt={tilt} zoom={zoom} for {secs}s")

def onvif_preset(ip, user, pw, preset=None):
    from onvif import ONVIFCamera
    cam = ONVIFCamera(ip, 80, user, pw)
    media = cam.create_media_service(); ptz = cam.create_ptz_service()
    tok = media.GetProfiles()[0].token
    presets = ptz.GetPresets({"ProfileToken": tok})
    for p in presets:
        print(" preset:", p.token, getattr(p, "Name", ""))
    if preset:
        ptz.GotoPreset({"ProfileToken": tok, "PresetToken": preset})
        print("-> went to preset", preset)

def examples():
    print("""# Hanwha SUNAPI (PTZ models):
curl -u USER:PASS "http://CAM_IP/stw-cgi/ptzcontrol.cgi?msubmenu=continuous&action=control&Pan=5&Tilt=0&Zoom=0"   # start panning
curl -u USER:PASS "http://CAM_IP/stw-cgi/ptzcontrol.cgi?msubmenu=stop&action=control&OperationType=All"           # stop
curl -u USER:PASS "http://CAM_IP/stw-cgi/ptzcontrol.cgi?msubmenu=absolute&action=control&Pan=180&Tilt=10&Zoom=2"  # absolute aim
# AXIS VAPIX:
curl -u USER:PASS "http://CAM_IP/axis-cgi/com/ptz.cgi?rpan=15"        # pan +15 deg
curl -u USER:PASS "http://CAM_IP/axis-cgi/com/ptz.cgi?gotoserverpresetname=Home"
# Grab a frame while you're at it:
curl -u USER:PASS "http://CAM_IP/stw-cgi/video.cgi?msubmenu=snapshot&action=view" -o snap.jpg   # Hanwha
# FlashPoint tier-3 note: SmokeyNet needs ~60s of STEADY frames -> aim, DWELL 3-5 min per strike sector, then move.""")

if __name__ == "__main__":
    a = sys.argv[1:] or ["help"]
    if a[0] == "discover": discover()
    elif a[0] == "onvif" and len(a) >= 4:
        kw = {}
        for flag in ("--pan", "--tilt", "--zoom", "--secs"):
            if flag in a: kw[flag[2:]] = float(a[a.index(flag) + 1])
        onvif_move(a[1], a[2], a[3], **kw)
    elif a[0] == "presets" and len(a) >= 4:
        onvif_preset(a[1], a[2], a[3], a[4] if len(a) > 4 else None)
    elif a[0] == "examples": examples()
    else:
        print(__doc__)
