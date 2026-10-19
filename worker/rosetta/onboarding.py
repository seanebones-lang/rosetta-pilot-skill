"""Local, machine-readable onboarding. No account creation or model invocation."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

from .common import Invalid, read_json, save_json
from .control import ROOT, calibrate, source_packet, targets, validate_calibration
from .sandbox import resolve_image

DEFAULT_IMAGE = 'python:3.12-slim-bookworm'


def protocol():
    result = read_json(ROOT/'catalog/agent-contract.json')
    return {**result, 'local_guide':str(ROOT/'docs/AGENT_QUICKSTART.md')}


def doctor(config_path=None, image=None):
    checks, actions = [], []
    config = None
    def check(name, passed, code, message, command=None):
        ready_messages = {
            'python':'Python meets the minimum supported version.',
            'platform':'The current platform is supported.',
            'docker':'Docker is installed.',
            'docker_daemon':'The existing Docker service responds.',
            'adapter_command':'The configured adapter executable exists; it has not been run.',
            'agent_identity':'The adapter and model identities are configured.',
            'state_directory':'A private state directory is configured.',
            'target':'An enabled reviewed target is configured.'}
        checks.append({'check':name,'passed':passed,'code':name.upper()+'_OK' if passed else code,
                       'message':ready_messages.get(name,message) if passed else message})
        if not passed:
            actions.append({'code':code,'message':message,'command':command,'automatic':False})
    check('python',sys.version_info >= (3,11),'PYTHON_VERSION','Use Python 3.11 or newer.')
    check('platform',os.name=='posix','PLATFORM_UNSUPPORTED','Use macOS or Linux; native Windows is unsupported.')
    if config_path:
        try:
            path=Path(config_path)
            if path.stat().st_size>65536:
                raise Invalid('oversized config')
            config=read_json(path)
            if not isinstance(config,dict):
                raise Invalid('config must be an object')
            check('config',True,'CONFIG_READABLE','Private configuration is readable.')
        except (OSError,ValueError):
            check('config',False,'CONFIG_UNREADABLE','Provide a readable local configuration JSON.')
    executable=shutil.which('docker')
    check('docker',bool(executable),'DOCKER_MISSING','Install Docker using your own approved setup process.')
    daemon=False
    if executable:
        try:
            result=subprocess.run([executable,'info','--format','{{.ServerVersion}}'],capture_output=True,timeout=5)
            daemon=result.returncode==0
        except (OSError,subprocess.SubprocessError):
            pass
        check('docker_daemon',daemon,'DOCKER_UNAVAILABLE','Start or repair your existing Docker service.')
    selected=image or (config or {}).get('image') or DEFAULT_IMAGE
    image_id=None
    if daemon:
        try:
            if not isinstance(selected,str) or not selected:
                raise Invalid('invalid image')
            image_id=resolve_image(selected)
            check('sandbox_image',True,'IMAGE_READY','An existing sandbox image resolves to an immutable ID.')
        except (Invalid,OSError,subprocess.SubprocessError):
            check('sandbox_image',False,'IMAGE_UNAVAILABLE','Choose an already-installed Python 3.12 image; Rosetta will not pull one.')
    if config is not None:
        command=config.get('agent_command')
        valid=isinstance(command,list) and bool(command) and all(isinstance(v,str) and v and '\x00' not in v for v in command)
        configured=valid and bool(shutil.which(command[0]))
        check('adapter_command',bool(configured),'ADAPTER_NOT_CONFIGURED','Configure an existing trusted executable adapter; doctor does not run it.')
        identity=config.get('agent_identity')
        check('agent_identity',isinstance(identity,dict) and all(isinstance(identity.get(k),str) and identity[k] for k in ['id','model']),
              'AGENT_IDENTITY_MISSING','Set the adapter ID and exact model in your private config.')
        state=config.get('state_dir')
        check('state_directory',isinstance(state,str) and bool(state),'STATE_MISSING','Choose a private state directory in your config.')
        target=next((t for t in targets() if t['id']==config.get('daily_target') and t.get('enabled')),None)
        check('target',target is not None,'TARGET_UNKNOWN','Choose an enabled reviewed target from rosetta targets.')
        if target and target['kind']!='calibration':
            try:
                source_packet(target)
                check('local_source_review',True,'SOURCE_REVIEW_CURRENT','Local source hashes and review age pass; live status is checked only at run time.')
            except (Invalid,OSError,ValueError):
                check('local_source_review',False,'SOURCE_REVIEW_REQUIRED','Refresh the reviewed target sources before research.')
        if all(c['passed'] for c in checks):
            try:
                validate_calibration(config)
                check('live_calibration',True,'CALIBRATION_CURRENT','The saved live calibration matches this local configuration.')
            except (Invalid,OSError,ValueError,KeyError,subprocess.SubprocessError):
                check('live_calibration',False,'CALIBRATION_REQUIRED','Run the actual adapter calibration within your approved provider budget.',
                      ['rosetta','calibrate','--config',str(config_path)])
    failed=[c['code'] for c in checks if not c['passed']]
    status=('needs_calibration' if failed==['CALIBRATION_REQUIRED'] else 'needs_setup') if failed else ('ready_for_bounded_run' if config is not None else 'demo_ready')
    if not actions:
        actions=[{'code':'RUN_BOUNDED_RESEARCH' if config is not None else 'TRY_OFFLINE_DEMO',
                  'command':['rosetta','daily','--config',str(config_path)] if config is not None else ['rosetta','demo','--state','YOUR_PRIVATE_DIRECTORY'],
                  'automatic':False}]
    return {'schema_version':1,'status':status,'checks':checks,'next_actions':actions,
            'image_id':image_id,'model_calls':0,'experiment_executions':0,'remote_connection_available':False}


def demo(state, image=DEFAULT_IMAGE):
    image_id=resolve_image(image)
    base=Path(state).expanduser().resolve()
    base.mkdir(parents=True,exist_ok=True,mode=0o700)
    directory=base/('demo-'+uuid.uuid4().hex)
    directory.mkdir(mode=0o700)
    graph={'vertices':5,'edges':[[0,1],[1,2],[2,3],[3,4],[4,0]]}
    plan={'protocol_version':1,'target_id':'calibration-c5','method_id':'construct-an-odd-cycle',
          'hypothesis':'Known offline calibration fixture; this is not a research discovery.',
          'python':'import json\nprint(json.dumps('+repr({'status':'candidate','certificate':graph})+'))\n'}
    proposal=directory/'fixture-proposal.json'
    save_json(proposal,plan)
    config={'state_dir':str(directory),'image':image_id,'agent_command':[],
            'agent_identity':{'id':'offline-fixture','model':'none'},'timezone':'America/Chicago','witness':None}
    gate=calibrate(config,proposal=proposal)
    if not gate['passed'] or gate['live_adapter_tested']:
        raise Invalid('offline demonstration classification failed')
    return {'schema_version':1,'status':'passed','test_kind':'offline_fixture','live_agent_tested':False,
            'live_research_unlocked':False,'provider_calls':0,'experiment_network':'none',
            'controls':gate['controls'],'state_directory':str(directory),'image_id':image_id,
            'next_action':{'code':'CONFIGURE_YOUR_ADAPTER','guide':str(ROOT/'docs/AGENT_QUICKSTART.md')}}
