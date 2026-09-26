"""OS-Ken OpenFlow 1.3 app for an operator-owned edge OVS bridge.

Run on Linux with ``osken-manager sfl/sdn/osken_controller.py``. The planner
atomically writes AWARENET_SDN_POLICY; this app polls it and installs only
explicit IPv4/TCP service flows on the configured bridge DPID and port set.
"""

import json
import os
from pathlib import Path

from os_ken.base import app_manager
from os_ken.controller import ofp_event
from os_ken.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from os_ken.lib import hub
from os_ken.ofproto import ofproto_v1_3

from sfl.sdn.policy import validate_policy


class AwareNetEdgeSDN(app_manager.OSKenApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    COOKIE = 0xA7A4E001
    PRIORITY = 200

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.path = Path(os.environ.get("AWARENET_SDN_POLICY", "out/sdn_routes.json"))
        self.dpid = int(os.environ["AWARENET_SDN_DPID"], 0)
        self.allowed_ports = {int(x) for x in os.environ["AWARENET_SDN_PORTS"].split(",")}
        self.ingress_port = int(os.environ["AWARENET_SDN_INGRESS_PORT"])
        self.service_ip = os.environ["AWARENET_SDN_SERVICE_IP"]
        self.service_port = int(os.environ["AWARENET_SDN_SERVICE_PORT"])
        self.datapath = None
        self.last_payload = None
        self.poller = hub.spawn(self._poll)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features(self, ev):
        if ev.msg.datapath.id == self.dpid:
            self.datapath = ev.msg.datapath
            self.last_payload = None
            self.logger.info("attached to owned OVS datapath %s", self.dpid)

    @set_ev_cls(ofp_event.EventOFPStateChange, MAIN_DISPATCHER)
    def switch_state(self, ev):
        if ev.datapath.id == self.dpid and ev.datapath is not self.datapath:
            self.datapath = ev.datapath
            self.last_payload = None

    def _poll(self):
        while True:
            try:
                if self.datapath and self.path.exists():
                    payload = self.path.read_bytes()
                    if payload != self.last_payload:
                        policy = json.loads(payload)
                        validate_policy(policy, self.allowed_ports, self.dpid,
                                        self.ingress_port, self.service_ip,
                                        self.service_port)
                        self._install(policy)
                        self.last_payload = payload
            except Exception:
                self.logger.exception("policy rejected or OpenFlow installation failed")
            hub.sleep(1)

    def _install(self, policy):
        dp = self.datapath
        ofp, parser = dp.ofproto, dp.ofproto_parser
        # Delete only flows bearing our cookie. Operator and other-app flows stay.
        dp.send_msg(parser.OFPFlowMod(
            datapath=dp, cookie=self.COOKIE, cookie_mask=0xFFFFFFFFFFFFFFFF,
            table_id=0, command=ofp.OFPFC_DELETE, out_port=ofp.OFPP_ANY,
            out_group=ofp.OFPG_ANY, match=parser.OFPMatch()))
        for rule in policy["rules"]:
            match = parser.OFPMatch(in_port=rule["in_port"], eth_type=0x0800,
                                    ipv4_src=rule["src_ip"], ipv4_dst=rule["dst_ip"],
                                    ip_proto=6, tcp_dst=rule["tcp_dst"])
            actions = [parser.OFPActionOutput(rule["out_port"])]
            instructions = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]
            dp.send_msg(parser.OFPFlowMod(
                datapath=dp, cookie=self.COOKIE, table_id=0,
                command=ofp.OFPFC_ADD, priority=self.PRIORITY,
                match=match, instructions=instructions))
            # Keep the gradient response on the same authorized tunnel path.
            reverse = parser.OFPMatch(in_port=rule["out_port"], eth_type=0x0800,
                                      ipv4_src=rule["dst_ip"], ipv4_dst=rule["src_ip"],
                                      ip_proto=6, tcp_src=rule["tcp_dst"])
            back = [parser.OFPActionOutput(rule["in_port"])]
            dp.send_msg(parser.OFPFlowMod(
                datapath=dp, cookie=self.COOKIE, table_id=0,
                command=ofp.OFPFC_ADD, priority=self.PRIORITY,
                match=reverse,
                instructions=[parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, back)]))
        dp.send_msg(parser.OFPBarrierRequest(dp))
        self.logger.info("requested %d AwareNet bidirectional service flows; switch verification still required",
                         2 * len(policy["rules"]))
