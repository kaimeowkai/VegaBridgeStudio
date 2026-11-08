"""Read-only migration evidence, not an APK converter or compatibility runtime."""
import json
import os
import re
import tomllib
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath

MAX_FILES=20000
MAX_TEXT=1024*1024
SKIP={'.git','.gradle','.idea','.venv','node_modules','build','dist','stage','private','secrets','captures','conversations','.vegabridge'}
SOURCE={'.java','.kt','.kts','.js','.jsx','.ts','.tsx','.c','.cc','.cpp','.cxx','.h','.hpp','.html','.css','.xml','.gradle'}
ASSETS={'.png','.jpg','.jpeg','.webp','.svg','.wav','.ogg','.mp3','.mp4','.ttf','.otf'}
RULES=[
 ('android-ui',r'\bandroidx\.(?:compose|appcompat|fragment)|\bandroid\.(?:app|view|widget)\b|<(?:LinearLayout|RelativeLayout|androidx\.)',
  'Rebuild Android screens/lifecycle as Vega React Native screens; preserve behavior and add TV focus navigation.'),
 ('android-storage',r'\bandroidx\.room|\bandroid\.database|\b(?:SharedPreferences|RoomDatabase|SQLiteDatabase)\b',
  'Define a storage adapter and data-format migration; verify a supported Vega implementation against the selected SDK.'),
 ('android-media',r'\bandroidx\.media3|com\.google\.android\.exoplayer2|\b(?:ExoPlayer|MediaCodec|MediaPlayer)\b',
  'Replace Android playback integration; separately qualify Vega playback, captions, DRM and lifecycle behavior.'),
 ('android-purchases-licensing',r'com\.android\.billingclient|com\.amazon\.(?:device\.(?:iap|drm)|venezia)|\b(?:PurchasingService|LicenseChecker)\b',
  'Implement a Vega entitlement/purchase adapter; verify purchase, restore and offline/error behavior. Android receipts and SDK binaries are not drop-in substitutes.'),
 ('google-services',r'com\.google\.(?:android\.gms|firebase)',
  'Inventory each Google service and choose a supported Vega or backend alternative; preserve authentication/data behavior.'),
 ('android-background',r'androidx\.work|\b(?:WorkManager|BroadcastReceiver|ForegroundService)\b|extends\s+Service\b',
  'Map background work and broadcasts to supported Vega lifecycle/service APIs and test foreground/background transitions.'),
 ('android-connectivity',r'\bandroid\.(?:bluetooth|net|nfc)\b|\b(?:WifiManager|NsdManager)\b',
  'Separate network protocols from Android discovery/hardware access; qualify corresponding Vega APIs and permissions.'),
 ('android-native-abi',r'\bjni\.h\b|\b(?:JNIEnv|JavaVM|ANativeWindow|__android_log_print)\b|<android/|\bcom\.facebook\.react\.(?:bridge|uimanager)',
  'Rebuild native code against the Vega toolchain; replace JNI/NDK and Android runtime dependencies, then expose an appropriate native interface.'),
 ('webview-bridge',r'\bandroid\.webkit|\b(?:WebView|addJavascriptInterface)\b',
  'Check whether web content is the primary UI. Reuse applicable web assets through Vega WebView and replace every Android JavaScript bridge.'),
 ('touch-input',r'\b(?:onTouchEvent|GestureDetector|MotionEvent)\b',
  'Design directional focus, Select/Back and remote navigation; touch behavior alone does not establish TV usability.'),
 ('android-platform-api',r'(?<![\w./:])(?:android|androidx)\.[A-Za-z_]',
  'Review all Android/AndroidX references, including APIs outside the specialized rules, and assign a supported Vega replacement or an explicit unresolved task.'),
]
PATTERNS=[(key,re.compile(pattern),action) for key,pattern,action in RULES]
REFERENCES=[
 'https://developer.amazon.com/apps-and-games/blogs/2026/10/port-your-tv-app-to-react-native-with-adbt',
 'https://www.developer.amazon.com/docs/adbt/port-fire-os-app-to-vega',
 'https://developer.amazon.com/docs/vega-api/2.0/porting-libraries',
 'https://developer.amazon.com/docs/vega/latest/app-management-com-tools',
]


def permissions(data):
    if not data.lstrip().startswith(b'<'):return [],'Binary manifest; permissions not decoded'
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():return [],'Manifest declarations refused'
    try:root=ET.fromstring(data)
    except ET.ParseError:return [],'Manifest XML could not be parsed'
    values={element.get('{http://schemas.android.com/apk/res/android}name','') for element in root.iter() if element.tag in {'uses-permission','uses-permission-sdk-23'}}
    return sorted(value for value in values if re.fullmatch(r'[A-Za-z][A-Za-z0-9_.]{0,180}',value)),'Plain XML inspected'


def base_report(name,kind):
    return {'schemaVersion':1,'inputName':name,'inputKind':kind,'readOnly':True,
        'directApkExecutionSupported':False,'assessmentOnly':True,
        'runtimeBoundary':'Vega does not provide the Android ART/Activity framework. A Linux kernel and matching CPU architecture do not make an APK or Android native library compatible.',
        'limitations':[],'references':REFERENCES}


def assess_apk(path):
    report=base_report(path.name,'APK inventory')
    if path.stat().st_size>512*1024*1024:raise ValueError('APK exceeds the 512 MiB assessment limit')
    with zipfile.ZipFile(path) as archive:
        entries=archive.infolist()
        if len(entries)>MAX_FILES:raise ValueError('APK has too many archive entries')
        names=[entry.filename for entry in entries]
        if any('..' in PurePosixPath(name).parts or name.startswith(('/','\\')) or '\\' in name or ':' in name for name in names):
            raise ValueError('Unsafe APK entry name')
        if len(names)!=len(set(names)):raise ValueError('Duplicate APK archive entries')
        if 'AndroidManifest.xml' not in names:raise ValueError('APK has no AndroidManifest.xml')
        manifest=archive.getinfo('AndroidManifest.xml')
        if manifest.file_size>MAX_TEXT:raise ValueError('APK manifest is too large')
        with archive.open(manifest) as source:data=source.read(MAX_TEXT+1)
        if len(data)>MAX_TEXT:raise ValueError('APK manifest is too large')
        declared,status=permissions(data)
        native=[name for name in names if re.fullmatch(r'lib/[^/]+/[^/]+\.so',name)]
        report.update({'recommendedPath':'Obtain source and create a separate Vega project; APK inspection alone cannot reconstruct or qualify a working app.',
            'dexFiles':sum(bool(re.fullmatch(r'classes[0-9]*\.dex',name)) for name in names),
            'nativeAbis':sorted({name.split('/')[1] for name in native}),'nativeLibraryCount':len(native),
            'manifestPermissions':declared,'manifestStatus':status,'archiveEntries':len(entries)})
    report['limitations']=['No DEX decompilation, execution, signature trust validation or semantic dependency analysis is performed.',
        'Android native ABI names identify Android builds, not Vega compatibility. Nothing is extracted or installed.']
    return report


def assess_source(root):
    report=base_report(root.name,'Source project');counts=Counter();assets=Counter();hits={key:set() for key,_,_ in PATTERNS}
    candidates=[];manifests=[];declared=set();dependencies={};unread=0;seen=0;limited=False;native=[];directory_errors=[]
    for directory,dirs,files in os.walk(root,followlinks=False,onerror=lambda error:directory_errors.append(True)):
        folder=Path(directory)
        dirs[:]=sorted(name for name in dirs if name not in SKIP and not name.startswith('.') and not (folder/name).is_symlink() and not (folder/name).is_junction())
        for name in sorted(files):
            seen+=1
            if seen>MAX_FILES:limited=True;break
            path=folder/name;relative=path.relative_to(root).as_posix();suffix=path.suffix.lower()
            if path.is_symlink() or path.is_junction() or not path.resolve().is_relative_to(root):continue
            if name.startswith('.') or suffix in {'.pem','.key','.p12','.pfx','.dpapi','.jks','.keystore'}:continue
            if suffix in ASSETS:assets[suffix]+=1;continue
            if suffix=='.so':native.append(relative);continue
            if suffix not in SOURCE and name not in {'package.json','libs.versions.toml'}:continue
            try:
                with path.open('rb') as source:data=source.read(MAX_TEXT+1)
                if len(data)>MAX_TEXT:unread+=1;continue
                text=data.decode('utf8')
            except (OSError,UnicodeError):unread+=1;continue
            if name=='package.json':
                try:package=json.loads(text)
                except ValueError:unread+=1;continue
                for key in ('dependencies','devDependencies'):
                    values=package.get(key,{}) if isinstance(package,dict) else {}
                    if isinstance(values,dict):
                        for dependency,version in values.items():
                            if re.fullmatch(r'(?:@[a-zA-Z0-9_.-]+/)?[a-zA-Z0-9_.-]+',dependency) and isinstance(version,str):
                                dependencies[dependency]='version declared' # Never export credential-bearing URLs or local dependency paths.
                continue
            if name=='libs.versions.toml':
                try:catalog=tomllib.loads(text)
                except ValueError:unread+=1;continue
                libraries=catalog.get('libraries',{})
                if not isinstance(libraries,dict):unread+=1;continue
                for value in libraries.values():
                    if isinstance(value,dict):
                        module=value.get('module') or str(value.get('group',''))+':'+str(value.get('name',''))
                        if isinstance(module,str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.-]*:[A-Za-z0-9_.-]+',module):dependencies[module]='module declared'
                continue
            if suffix in {'.gradle','.kts'}:
                for module in re.findall(r'\b(?:implementation|api|compileOnly|runtimeOnly|testImplementation)\s*\(?\s*[\"\']([A-Za-z_][A-Za-z0-9_.-]*:[A-Za-z0-9_.-]+)',text):
                    dependencies[module]='module declared'
            counts[suffix]+=1
            if name=='AndroidManifest.xml':
                values,status=permissions(data);declared.update(values);manifests.append({'path':relative,'status':status})
            matched=False
            for key,pattern,_ in PATTERNS:
                if pattern.search(text):hits[key].add(relative);matched=True
            if suffix in {'.kt','.java','.c','.cc','.cpp','.cxx'} and not matched:candidates.append(relative)
        if limited:break
    findings=[{'id':key,'files':sorted(hits[key])[:20],'totalFiles':len(hits[key]),'action':action} for key,_,action in PATTERNS if hits[key]]
    android=bool(manifests or hits['android-ui'] or hits['android-storage'] or hits['android-connectivity']);rn='react-native' in dependencies or any(name.startswith('@amazon-devices/react-native') for name in dependencies)
    web=bool(counts['.html'])
    route='React Native source migration' if rn else ('Native Android source migration' if android else ('Web content assessment' if web else 'Manual classification required'))
    report.update({'recommendedPath':route,'sourceLanguageCounts':dict(sorted((key,value) for key,value in counts.items() if value)),
        'assetCounts':dict(sorted(assets.items())),'dependencyNames':sorted(dependencies),'manifestPermissions':sorted(declared),
        'manifests':manifests,'findings':findings,'logicReviewCandidates':sorted(candidates)[:50],
        'logicCandidateCount':len(candidates),'prebuiltNativeLibraries':native[:50],
        'webContentPresent':web,'filesConsidered':min(seen,MAX_FILES),'scanLimited':limited,'unreadableOrOversizeTextFiles':unread,'unreadableDirectories':len(directory_errors)})
    report['limitations']=['Static text indicators can miss indirect dependencies or match comments. Findings are evidence for review, not a complete API inventory.',
        'A logic candidate has no recognized Android marker; this does not prove portability or provide a translated implementation.',
        'Web content presence does not establish that WebView is the primary UI. React Native dependencies still need version/native-module checks.',
        'No source file, build script, dependency, signing identity, SDK setting or device is modified or executed.']
    if limited or unread or directory_errors:report['limitations'].append('The scan is incomplete; review omitted files before using this plan.')
    return report


def assess_android(path):
    path=Path(path)
    if path.is_symlink() or path.is_junction():raise ValueError('Select the actual input, not a linked directory or file')
    path=path.resolve()
    if path.is_dir():return assess_source(path)
    if path.is_file() and path.suffix.lower()=='.apk':return assess_apk(path)
    raise ValueError('Select an Android source directory or an APK file')


def render_plan(report):
    lines=['# Android to Vega assessment','',f"Input type: {report['inputKind']}",f"Suggested route: {report['recommendedPath']}",'',report['runtimeBoundary'],'',
        'This is a local read-only assessment. It does not convert, execute or sideload an APK.','',
        '## Evidence','']
    if report['inputKind']=='APK inventory':
        lines += [f"DEX files: {report['dexFiles']}; native libraries: {report['nativeLibraryCount']}.",f"Manifest: {report['manifestStatus']}.",'Obtain source before planning code reuse or API replacements.']
    else:
        for finding in report['findings']:lines += [f"- **{finding['id']}** ({finding['totalFiles']} file(s)): {finding['action']}"]
        if not report['findings']:lines += ['No configured Android indicators were detected. Manual classification is still required.']
        lines += ['',f"Business/native logic candidates for manual review: {report['logicCandidateCount']}. This is not a compatibility score."]
    lines += ['', '## Working methodology','',
        '1. Record source features, screens, input behavior, data formats and external services. Keep Android and Vega output separate.',
        '2. Define platform adapters around storage, media, purchases, networking and lifecycle. Assign each dependency a verified Vega implementation or an unresolved task.',
        '3. Preserve expected behavior with golden input/output tests. Review reusable JS/web assets and rebuild eligible C/C++ against Vega; translate selected Java/Kotlin logic only with equivalent tests.',
        '4. Build one complete vertical slice: start, navigate with a TV remote, perform the main action, persist state, and reopen it. Track omitted features explicitly.',
        '5. Produce a signed Vega VPKG with the correct target architecture/runtime. Use Studio\'s existing install/run path to sideload that VPKG into the Vega VM.',
        '6. Verify focus/Back behavior, lifecycle, errors, persistence and the original logic tests. Qualify platform services separately before claiming feature parity.',
        '', '## Assessment limits','']
    lines += ['- '+value for value in report['limitations']]
    lines += ['', '## Official references','']+['- '+url for url in report['references']]
    return '\n'.join(lines)+'\n'


def write_plan(report,input_path,destination):
    root=Path(input_path).resolve();destination=Path(destination).resolve()
    if destination==root or (root.is_dir() and destination.is_relative_to(root)):
        raise ValueError('Save the assessment outside the input project to keep that project read-only')
    destination.parent.mkdir(parents=True,exist_ok=True)
    with destination.open('x',encoding='utf8') as output:output.write(render_plan(report))
    return str(destination)
