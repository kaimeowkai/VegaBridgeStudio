"""Read-only discovery of owner-supplied SDK headers and link libraries."""
from pathlib import Path
from .native_build import TARGETS


def catalog_sdk(root,arch='x86_64',query='',limit=500,api_root=''):
    if arch not in TARGETS:raise ValueError('Unsupported SDK architecture')
    base=(Path(root)/('sysroot-'+arch)).resolve()
    if not (base/'usr/include').is_dir():raise ValueError('Choose an SDK root containing sysroot-'+arch)
    query=query.casefold().strip()
    if len(query)>200:raise ValueError('SDK search is limited to 200 characters')
    results=[]
    total=0
    roots=[(base/'usr/include','Header',base),(base/'usr/lib','Library',base)]
    if api_root:
        api=(Path(api_root)/arch).resolve()
        if not (api/'include').is_dir():raise ValueError('API root must contain '+arch+'/include')
        roots += [(api/'include','API header / contract',api),(api/'lib','Library',api)]
    for folder,kind,boundary in roots:
        for path in folder.rglob('*'):
            if not path.is_file() or path.is_symlink():continue
            if not path.resolve().is_relative_to(boundary):continue
            rel=path.relative_to(boundary).as_posix()
            if kind=='Library' and not (path.name.endswith(('.a','.so')) or '.so.' in path.name):continue
            if query and query not in rel.casefold():continue
            total+=1
            if len(results)<limit:results.append({'kind':kind,'relative':rel,'path':str(path),'bytes':path.stat().st_size})
    return {'architecture':arch,'root':str(base),'matches':total,'truncated':total>limit,'items':results,
        'note':'Presence is not proof of API availability, required manifest contracts, privileges or runtime compatibility.'}
