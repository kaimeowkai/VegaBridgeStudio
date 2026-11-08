"""Versioned shared mapping plans; no per-application source rewrites."""
REGISTRY_VERSION=1
REGISTRY={
 'business-logic':('Shared application logic',['shared-logic-tests','shared-language-translation','unresolved'],
  'Reuse or translate platform-neutral behavior through shared tooling; prove equivalence with input/output tests.'),
 'package-runtime':('Packaging and runtime',['vega-native-package','android-runtime-research','unresolved'],
  'Choose a Vega package output or unchanged-APK runtime research. Neither path is an implemented universal converter.'),
 'tv-input':('TV navigation',['shared-tv-focus','unresolved'],
  'Centralize directional focus, Select and Back behavior; retain per-feature behavior tests.'),
 'android-ui':('Android UI and lifecycle',['shared-react-native-ui','android-runtime-research','unresolved'],
  'Map framework UI/lifecycle behavior through a common implementation, rather than hand-writing one app at a time.'),
 'android-storage':('Android storage',['shared-vega-storage','preserve-data-format','unresolved'],
  'Use a common storage interface and preserve existing serialized data formats; verify the selected SDK backend.'),
 'android-media':('Android playback',['shared-vega-player','android-runtime-research','unresolved'],
  'Qualify playback, captions and hardware decoding through a shared backend; do not substitute a silent stub.'),
 'android-purchases-licensing':('Purchases and licensing',['shared-entitlement-interface','android-runtime-research','unresolved'],
  'Keep provider-specific receipts, keys and restore behavior explicit. A framework mapping does not prove entitlement compatibility.'),
 'google-services':('Google services',['shared-service-interface','android-runtime-research','unresolved'],
  'Record external service requirements and unresolved platform dependencies.'),
 'android-background':('Background work',['shared-vega-lifecycle','android-runtime-research','unresolved'],
  'Define lifecycle and task scheduling semantics in a reusable adapter.'),
 'android-connectivity':('Networking and hardware',['shared-connectivity-interface','android-runtime-research','unresolved'],
  'Separate reusable network protocols from device discovery and hardware APIs.'),
 'android-native-abi':('JNI and native ABI',['rebuild-native-core','android-runtime-research','unresolved'],
  'Rebuild portable native code or provide a compatible Android runtime; Android native libraries are not Vega binaries.'),
 'webview-bridge':('WebView and native bridge',['shared-webview-bridge','android-runtime-research','unresolved'],
  'Reuse web content where appropriate and implement Android bridge contracts through a shared backend.'),
 'touch-input':('Touch interaction',['shared-tv-focus','virtual-input-runtime','unresolved'],
  'Map touch and remote input through common input handling and verify navigation behavior.'),
 'android-platform-api':('Remaining framework APIs',['shared-api-registry','android-runtime-research','unresolved'],
  'Track API coverage centrally; missing APIs stay unresolved instead of becoming successful no-ops.'),
 'apk-source':('APK-only input',['android-runtime-research','source-required','unresolved'],
  'APK inventory can guide runtime research. This tool has not recovered or converted its source.'),
}
STATES={'unreviewed':'Unreviewed','planned':'Plan reviewed','blocked':'Blocked'}


def adapter_rows(report):
    findings={value['id']:value for value in report.get('findings',[])}
    ids=['business-logic','package-runtime','tv-input']+list(findings)
    if report['inputKind']=='APK inventory':ids.append('apk-source')
    rows=[]
    for key in dict.fromkeys(ids):
        if key not in REGISTRY:continue
        label,options,description=REGISTRY[key];finding=findings.get(key,{})
        rows.append({'id':key,'feature':label,'adapter':options[0],'status':'unreviewed','notes':'',
            'evidence':finding.get('files',[]),'evidenceCount':finding.get('totalFiles',0),
            'description':description,'implementationVerified':False})
    return rows


def validate_rows(report,rows):
    expected={row['id'] for row in adapter_rows(report)}
    if len(rows)!=len(expected) or {row.get('id') for row in rows}!=expected:raise ValueError('Adapter coverage differs from the assessment')
    checked=[]
    for row in rows:
        key=row['id']
        if row.get('adapter') not in REGISTRY[key][1] or row.get('status') not in STATES:raise ValueError('Invalid adapter choice or review state')
        notes=row.get('notes','')
        if not isinstance(notes,str) or len(notes)>4000:raise ValueError('Adapter notes exceed 4000 characters')
        checked.append({'id':key,'adapter':row['adapter'],'status':row['status'],'notes':notes,'implementationVerified':False})
    return checked
