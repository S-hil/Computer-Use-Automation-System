"""
ApexCore 9.4 Banking Servicing Console - Local Mock Application.
Simulates a legacy, intentionally hostile enterprise banking application:
- Deeply nested tables and non-semantic layouts
- ASP.NET / JSP style dynamic element names (e.g. ctl00$MainContent$txtMemberId)
- Zero data-testid attributes
- Realistic bank workflows:
    * Member search and balance inquiry
    * Business outcome: "Record Not Found" (AC-404)
    * Recoverable interstitial: Session inactivity modal
    * High-risk operation & supervisor escalation gate
"""

import http.server
import json
import os
import socketserver
import sys
import threading
import urllib.parse
from typing import Optional

PORT = 8088

MEMBERS_DB = {
    "MEM-7701": {
        "member_id": "MEM-7701",
        "full_name": "Alice Smith",
        "ssn_masked": "***-**-8821",
        "status": "Active / Premier Tier 1",
        "branch": "Metro West Branch #04",
        "accounts": [
            {"type": "Savings", "account_num": "SAV-4091-88", "balance": "$14,250.80", "available": "$14,250.80", "apy": "4.25%"},
            {"type": "Checking", "account_num": "CHK-8812-01", "balance": "$3,120.50", "available": "$3,070.50", "apy": "0.10%"},
            {"type": "Certificate of Deposit", "account_num": "CD-1092-55", "balance": "$25,000.00", "available": "$0.00", "apy": "5.10%"}
        ]
    },
    "MEM-3302": {
        "member_id": "MEM-3302",
        "full_name": "Robert J. Davis",
        "ssn_masked": "***-**-4419",
        "status": "Active / Standard",
        "branch": "Downtown HQ #01",
        "accounts": [
            {"type": "Savings", "account_num": "SAV-9182-12", "balance": "$1,450.00", "available": "$1,450.00", "apy": "1.50%"},
            {"type": "Checking", "account_num": "CHK-3021-99", "balance": "$840.25", "available": "$840.25", "apy": "0.05%"}
        ]
    }
}


def render_html(content: str, title: str = "ApexCore 9.4 Servicing Console", show_interstitial: bool = False) -> str:
    interstitial_html = ""
    if show_interstitial:
        interstitial_html = """
        <div id="ctl00_dlgSessionWarning" class="legacy-modal-overlay" style="display:flex;">
            <div class="legacy-modal-box">
                <div class="legacy-modal-header">Security Compliance Notice</div>
                <div class="legacy-modal-body">
                    <p><strong>Warning:</strong> Session inactivity threshold approaching (120s remaining).</p>
                    <p>To preserve audit state under GLBA compliance, please acknowledge this prompt.</p>
                </div>
                <div class="legacy-modal-footer">
                    <button id="ctl00_btnKeepSessionAlive" onclick="document.getElementById('ctl00_dlgSessionWarning').style.display='none';">Extend Session</button>
                </div>
            </div>
        </div>
        """

    return f"""<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN" "http://www.w3.org/TR/html4/loose.dtd">
<html>
<head>
    <title>{title}</title>
    <meta http-equiv="Content-Type" content="text/html; charset=iso-8859-1">
    <style>
        body {{
            font-family: Tahoma, Verdana, Arial, sans-serif;
            font-size: 11px;
            background-color: #ECE9D8;
            margin: 0;
            padding: 0;
            color: #000;
        }}
        .header-bar {{
            background: linear-gradient(to bottom, #0A246A 0%, #A6CAF0 100%);
            color: white;
            padding: 4px 8px;
            font-weight: bold;
            font-size: 12px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .sub-header {{
            background-color: #D4D0C8;
            border-bottom: 1px solid #808080;
            padding: 3px 6px;
            font-size: 11px;
        }}
        .workspace {{
            padding: 10px;
        }}
        .groupbox {{
            border: 1px solid #808080;
            padding: 8px;
            margin-bottom: 10px;
            background-color: #F5F4EA;
        }}
        .groupbox legend {{
            font-weight: bold;
            color: #0A246A;
            padding: 0 4px;
        }}
        .legacy-table {{
            border-collapse: collapse;
            width: 100%;
            background-color: #FFFFFF;
            border: 1px solid #7F9DB9;
        }}
        .legacy-table th {{
            background-color: #D4D0C8;
            border: 1px solid #808080;
            padding: 4px;
            text-align: left;
            font-size: 11px;
        }}
        .legacy-table td {{
            border: 1px solid #D4D0C8;
            padding: 4px 6px;
            font-size: 11px;
        }}
        .legacy-table tr:hover {{
            background-color: #FFFFCC;
        }}
        .btn {{
            font-family: Tahoma, Verdana, Arial;
            font-size: 11px;
            padding: 2px 10px;
            background-color: #ECE9D8;
            border: 2px outset #FFFFFF;
            cursor: pointer;
        }}
        .btn:active {{
            border: 2px inset #FFFFFF;
        }}
        .txtbox {{
            font-family: Tahoma, Verdana, Arial;
            font-size: 11px;
            border: 1px solid #7F9DB9;
            padding: 2px 4px;
        }}
        .error-panel {{
            background-color: #FFEEEE;
            border: 1px solid #CC0000;
            color: #990000;
            padding: 8px;
            margin-bottom: 10px;
            font-weight: bold;
        }}
        .success-panel {{
            background-color: #EEFFEE;
            border: 1px solid #008800;
            color: #006600;
            padding: 8px;
            margin-bottom: 10px;
            font-weight: bold;
        }}
        .nav-tabs {{
            display: flex;
            gap: 2px;
            border-bottom: 1px solid #808080;
            margin-bottom: 8px;
        }}
        .tab-item {{
            background-color: #D4D0C8;
            border: 1px solid #808080;
            border-bottom: none;
            padding: 4px 12px;
            cursor: pointer;
            text-decoration: none;
            color: #000;
        }}
        .tab-item.active {{
            background-color: #F5F4EA;
            font-weight: bold;
            border-bottom: 1px solid #F5F4EA;
            margin-bottom: -1px;
        }}
        .legacy-modal-overlay {{
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background-color: rgba(0,0,0,0.5);
            align-items: center;
            justify-content: center;
            z-index: 9999;
        }}
        .legacy-modal-box {{
            background-color: #ECE9D8;
            border: 3px outset #FFFFFF;
            width: 380px;
            box-shadow: 4px 4px 10px rgba(0,0,0,0.5);
        }}
        .legacy-modal-header {{
            background: #0A246A;
            color: #FFF;
            padding: 4px 8px;
            font-weight: bold;
        }}
        .legacy-modal-body {{
            padding: 12px;
        }}
        .legacy-modal-footer {{
            padding: 8px;
            text-align: right;
            border-top: 1px solid #808080;
        }}
    </style>
</head>
<body>
    <div class="header-bar">
        <span>ApexCore Enterprise Banking System [v9.4.11-PROD]</span>
        <span>Operator: SVC_AGENT_901 | Institution: First Fidelity Credit Union #8820</span>
    </div>
    <div class="sub-header">
        Terminal ID: T091 | District: Midwest-04 | Encryption: 3DES-ACTIVE | Compliance: GLBA/SOX
    </div>
    {interstitial_html}
    <div class="workspace">
        {content}
    </div>
</body>
</html>
"""


class ApexCoreHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Silence routine request logging to keep console clean
        return

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        path = parsed.path

        show_interstitial = params.get("interstitial", ["false"])[0].lower() == "true"

        if path in ("/", "/apexcore", "/apexcore/"):
            self.render_search_page(show_interstitial=show_interstitial)
        elif path == "/apexcore/member/search":
            member_id = params.get("ctl00$MainContent$txtMemberId", [""])[0].strip().upper()
            if not member_id:
                member_id = params.get("member_id", [""])[0].strip().upper()
            self.handle_member_search(member_id, params)
        elif path == "/apexcore/member/detail":
            member_id = params.get("id", [""])[0].strip().upper()
            tab = params.get("tab", ["summary"])[0]
            self.render_member_detail(member_id, tab, params)
        elif path == "/apexcore/member/transfer":
            member_id = params.get("id", [""])[0].strip().upper()
            self.render_transfer_page(member_id, params)
        elif path == "/apexcore/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "running", "version": "9.4.11"}).encode())
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"404 Not Found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length).decode()
        post_params = urllib.parse.parse_qs(post_data)

        if parsed.path in ("/apexcore/member/search", "/apexcore/"):
            member_id = post_params.get("ctl00$MainContent$txtMemberId", [""])[0].strip().upper()
            self.handle_member_search(member_id, post_params)
        elif parsed.path == "/apexcore/member/transfer/submit":
            self.handle_transfer_submit(post_params)
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"404 Not Found")

    def render_search_page(self, error_message: Optional[str] = None, show_interstitial: bool = False):
        error_html = ""
        if error_message:
            error_html = f"""
            <div id="ctl00_MainContent_pnlError" class="error-panel" role="alert">
                <strong>Core System Alert:</strong> {error_message}
            </div>
            """

        content = f"""
        {error_html}
        <fieldset class="groupbox">
            <legend>Member Record Lookup Service</legend>
            <form id="aspnetForm" method="GET" action="/apexcore/member/search">
                <table cellpadding="4" cellspacing="2" border="0">
                    <tr>
                        <td align="right"><strong>Lookup Criteria:</strong></td>
                        <td>
                            <select name="ctl00$MainContent$ddlSearchType" id="ctl00_MainContent_ddlSearchType" class="txtbox">
                                <option value="MEMBER_ID" selected>Member ID Number</option>
                                <option value="SSN_TIN">Taxpayer Identification (TIN/SSN)</option>
                                <option value="ACCT_NUM">Primary Account Number</option>
                            </select>
                        </td>
                    </tr>
                    <tr>
                        <td align="right"><strong>Member ID:</strong></td>
                        <td>
                            <!-- Deliberately using legacy ASP.NET generated name/id without test IDs -->
                            <input type="text"
                                   name="ctl00$MainContent$txtMemberId"
                                   id="ctl00_MainContent_txtMemberId"
                                   class="txtbox"
                                   size="18"
                                   aria-label="Member ID"
                                   value="" />
                            <span style="color:#666; font-size:10px;"> (Format: MEM-XXXX, e.g. MEM-7701)</span>
                        </td>
                    </tr>
                    <tr>
                        <td align="right"><strong>District Unit:</strong></td>
                        <td>
                            <input type="text" name="ctl00$MainContent$txtDistrict" id="ctl00_MainContent_txtDistrict" class="txtbox" size="6" value="MW-04" readonly />
                        </td>
                    </tr>
                    <tr>
                        <td>&nbsp;</td>
                        <td>
                            <button type="submit"
                                    id="ctl00_MainContent_btnSearch"
                                    name="ctl00$MainContent$btnSearch"
                                    class="btn"
                                    aria-label="Execute Inquiry">
                                <strong>Execute Inquiry</strong>
                            </button>
                            &nbsp;
                            <input type="reset" class="btn" value="Clear Form" />
                        </td>
                    </tr>
                </table>
            </form>
        </fieldset>

        <div style="margin-top:15px; font-size:10px; color:#555;">
            <strong>Operator Quick Reference:</strong> Valid test members: <code>MEM-7701</code> (Alice Smith), <code>MEM-3302</code> (Robert Davis). Non-existent member: <code>MEM-9999</code>.
        </div>
        """
        html = render_html(content, "Member Inquiry - ApexCore 9.4", show_interstitial=show_interstitial)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def handle_member_search(self, member_id: str, params: dict):
        if not member_id:
            self.render_search_page(error_message="Parameter missing: Member ID cannot be empty.")
            return

        if member_id in MEMBERS_DB:
            # Found - redirect or render member detail
            self.send_response(302)
            self.send_header("Location", f"/apexcore/member/detail?id={urllib.parse.quote(member_id)}&tab=summary")
            self.end_headers()
        else:
            # Expected Business Outcome: Member Not Found
            error_msg = f"AC-404: Member Record [{member_id}] not found in district database. Verify identifier."
            self.render_search_page(error_message=error_msg)

    def render_member_detail(self, member_id: str, tab: str, params: dict):
        member = MEMBERS_DB.get(member_id)
        if not member:
            self.render_search_page(error_message=f"AC-404: Member [{member_id}] not found.")
            return

        accounts_rows = ""
        savings_balance = "$0.00"
        for acct in member["accounts"]:
            if acct["type"] == "Savings":
                savings_balance = acct["balance"]
            accounts_rows += f"""
            <tr>
                <td><strong>{acct['type']}</strong></td>
                <td>{acct['account_num']}</td>
                <td align="right" style="font-weight:bold; color:#0A246A;">{acct['balance']}</td>
                <td align="right">{acct['available']}</td>
                <td align="center">{acct['apy']}</td>
                <td align="center">
                    <a href="/apexcore/member/transfer?id={member_id}&acct={acct['account_num']}" class="btn" style="text-decoration:none;">Action</a>
                </td>
            </tr>
            """

        content = f"""
        <div style="display:flex; justify-content:space-between; align-items:flex-end; margin-bottom: 6px;">
            <div>
                <span style="font-size:14px; font-weight:bold; color:#0A246A;">Member Profile: {member['full_name']}</span>
                <span style="font-size:11px; color:#555;"> (ID: <span id="lblMemberId">{member['member_id']}</span> | SSN: {member['ssn_masked']})</span>
            </div>
            <div>
                <a href="/apexcore" class="btn" style="text-decoration:none;">&laquo; New Inquiry</a>
            </div>
        </div>

        <div class="nav-tabs" role="tablist">
            <a href="/apexcore/member/detail?id={member_id}&tab=summary" class="tab-item {'active' if tab=='summary' else ''}" role="tab">Account Summary</a>
            <a href="/apexcore/member/detail?id={member_id}&tab=profile" class="tab-item {'active' if tab=='profile' else ''}" role="tab">Demographics & KYC</a>
            <a href="/apexcore/member/detail?id={member_id}&tab=history" class="tab-item {'active' if tab=='history' else ''}" role="tab">Audit Log</a>
            <a href="/apexcore/member/transfer?id={member_id}" class="tab-item" role="tab" style="color:#990000; font-weight:bold;">Dual-Control Actions</a>
        </div>

        <fieldset class="groupbox">
            <legend>Institutional Status & Relationship</legend>
            <table cellpadding="2" cellspacing="2" border="0" width="100%">
                <tr>
                    <td width="15%"><strong>Relationship Status:</strong></td>
                    <td width="35%"><span style="color:green; font-weight:bold;">{member['status']}</span></td>
                    <td width="15%"><strong>Home Branch:</strong></td>
                    <td width="35%">{member['branch']}</td>
                </tr>
            </table>
        </fieldset>

        <fieldset class="groupbox">
            <legend>Account Balances & Positions</legend>
            <div id="ctl00_MainContent_pnlAccountsGrid">
                <!-- Deeply nested table structure typical of legacy banking cores -->
                <table class="legacy-table" id="gvAccounts" summary="Active Depository Accounts">
                    <thead>
                        <tr>
                            <th>Account Type</th>
                            <th>Account Number</th>
                            <th style="text-align:right;">Current Ledger Balance</th>
                            <th style="text-align:right;">Available Funds</th>
                            <th style="text-align:center;">Yield (APY)</th>
                            <th style="text-align:center;">Servicing</th>
                        </tr>
                    </thead>
                    <tbody>
                        {accounts_rows}
                    </tbody>
                </table>
            </div>
            <div style="margin-top:8px; text-align:right;">
                <span style="font-size:12px; font-weight:bold;">Primary Savings Balance: </span>
                <span id="lblPrimarySavingsBalance" style="font-size:13px; font-weight:bold; color:#0A246A;">{savings_balance}</span>
            </div>
        </fieldset>
        """

        html = render_html(content, f"Member Detail: {member['full_name']} - ApexCore 9.4")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def render_transfer_page(self, member_id: str, params: dict):
        member = MEMBERS_DB.get(member_id)
        if not member:
            self.render_search_page(error_message="Member not found")
            return

        supervisor_pin_required = params.get("supervisor_gate", ["true"])[0] == "true"
        override_success = params.get("approved", ["false"])[0] == "true"

        status_banner = ""
        if override_success:
            status_banner = """
            <div id="pnlSupervisorApprovalSuccess" class="success-panel" role="alert">
                <strong>SUPERVISOR OVERRIDE VERIFIED:</strong> Security token validated by Supervisor #SUP-8802. Transaction cleared.
            </div>
            """

        content = f"""
        {status_banner}
        <div style="margin-bottom:8px;">
            <a href="/apexcore/member/detail?id={member_id}" class="btn" style="text-decoration:none;">&laquo; Back to Member Detail</a>
        </div>

        <fieldset class="groupbox">
            <legend>High-Risk / Dual-Control Fund Release</legend>
            <p style="color:#B00; font-weight:bold;">
                WARNING: Fund release or account freeze is an IRREVERSIBLE action requiring dual-authorization under Banking Rule 802.
            </p>
            <form id="frmWireTransfer" method="POST" action="/apexcore/member/transfer/submit">
                <input type="hidden" name="member_id" value="{member_id}" />
                <table cellpadding="4" cellspacing="2" border="0">
                    <tr>
                        <td align="right"><strong>Member:</strong></td>
                        <td>{member['full_name']} ({member['member_id']})</td>
                    </tr>
                    <tr>
                        <td align="right"><strong>Target Action:</strong></td>
                        <td>
                            <select name="action_type" id="ddlActionType" class="txtbox">
                                <option value="WIRE_TRANSFER">Outbound FedWire Release ($5,000.00)</option>
                                <option value="ACCOUNT_FREEZE">Emergency Administrative Freeze</option>
                            </select>
                        </td>
                    </tr>
                    <tr>
                        <td align="right"><strong>Supervisor PIN:</strong></td>
                        <td>
                            <input type="password"
                                   name="supervisor_pin"
                                   id="txtSupervisorPin"
                                   class="txtbox"
                                   size="10"
                                   placeholder="6-digit PIN"
                                   aria-label="Supervisor PIN" />
                            <span style="color:#666; font-size:10px;"> (Required for Dual-Control Override, e.g. 902104)</span>
                        </td>
                    </tr>
                    <tr>
                        <td>&nbsp;</td>
                        <td>
                            <button type="submit"
                                    id="btnAuthorizeWire"
                                    name="btnAuthorizeWire"
                                    class="btn"
                                    style="color:#990000; font-weight:bold;"
                                    aria-label="Submit Dual Control Action">
                                Execute High-Risk Operation
                            </button>
                        </td>
                    </tr>
                </table>
            </form>
        </fieldset>
        """
        html = render_html(content, "High-Risk Servicing Gate - ApexCore 9.4")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def handle_transfer_submit(self, post_params: dict):
        member_id = post_params.get("member_id", [""])[0]
        pin = post_params.get("supervisor_pin", [""])[0]

        if pin == "902104":
            # Approved supervisor PIN
            self.send_response(302)
            self.send_header("Location", f"/apexcore/member/transfer?id={member_id}&supervisor_gate=false&approved=true")
            self.end_headers()
        else:
            # Blocked / Escalation trigger
            error_html = f"""
            <div id="pnlDualControlBlocked" class="error-panel" role="alert">
                <strong>CRITICAL SECURITY STOP (Dual-Control Lockout):</strong> Invalid or missing Supervisor PIN.
                Human Supervisor intervention required to release live session lock.
            </div>
            """
            member = MEMBERS_DB.get(member_id, {"full_name": "Unknown", "member_id": member_id})
            content = f"""
            {error_html}
            <div style="margin-bottom:8px;">
                <a href="/apexcore/member/transfer?id={member_id}" class="btn" style="text-decoration:none;">Retry PIN Entry</a>
            </div>
            <fieldset class="groupbox">
                <legend>Supervisor Live Session Override Console</legend>
                <p>An authorized supervisor must enter their credentials below to release the automated session:</p>
                <form method="POST" action="/apexcore/member/transfer/submit">
                    <input type="hidden" name="member_id" value="{member_id}" />
                    <input type="password" id="txtSupervisorOverridePin" name="supervisor_pin" class="txtbox" size="10" placeholder="PIN: 902104" />
                    <button type="submit" id="btnSupervisorOverrideApprove" class="btn">Approve & Release Session</button>
                </form>
            </fieldset>
            """
            html = render_html(content, "Supervisor Gate - Dual Control Lockout")
            self.send_response(403)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))


class ApexCoreServer:
    def __init__(self, port: int = PORT):
        self.port = port
        self.server: Optional[socketserver.TCPServer] = None
        self.thread: Optional[threading.Thread] = None

    def start(self):
        socketserver.TCPServer.allow_reuse_address = True
        self.server = socketserver.TCPServer(("127.0.0.1", self.port), ApexCoreHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return f"http://127.0.0.1:{self.port}/apexcore"

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()


if __name__ == "__main__":
    server = ApexCoreServer(PORT)
    url = server.start()
    print(f"ApexCore 9.4 Servicing Console running at: {url}")
    try:
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        server.stop()
        print("ApexCore server stopped.")
