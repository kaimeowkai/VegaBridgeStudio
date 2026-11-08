"""Source Map v3 position mapping for original project JS/TS/JSX/TSX files."""
from bisect import bisect_right
from pathlib import Path
from urllib.parse import unquote,urlsplit

ALPHABET='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
VALUES={value:index for index,value in enumerate(ALPHABET)}


def vlq(segment):
    values=[];number=0;shift=0
    for character in segment:
        if character not in VALUES:raise ValueError('Invalid source-map Base64 character')
        value=VALUES[character];number|=(value&31)<<shift
        if value&32:
            shift+=5
            if shift>35:raise ValueError('Oversized source-map VLQ value')
        else:
            values.append(-(number>>1) if number&1 else number>>1);number=0;shift=0
    if shift:raise ValueError('Truncated source-map VLQ value')
    return values


class SourceMap:
    def __init__(self,data,project):
        self.project=Path(project).resolve();self.lines={};self.reverse={};self.contents={};self.count=0
        self._parse(data)
        for entries in self.lines.values():entries.sort(key=lambda item:item[0])
        for entries in self.reverse.values():entries.sort()

    def source_path(self,source,root=''):
        if not isinstance(source,str):return None
        source=unquote(source).replace('\\','/');root=unquote(root).replace('\\','/')
        if source.startswith('file:'):
            source=urlsplit(source).path
            if len(source)>3 and source[0]=='/' and source[2]==':':source=source[1:]
        elif '://' in source:return None
        path=Path(source)
        if not path.is_absolute():path=Path(root)/path if Path(root).is_absolute() else self.project/root/path
        path=path.resolve()
        if not path.is_relative_to(self.project) or any(p in {'node_modules','.git','.vegabridge','private','secrets','build','stage'} for p in path.relative_to(self.project).parts):return None
        return path

    def _parse(self,data,base_line=0,base_column=0,depth=0):
        if depth>8 or not isinstance(data,dict) or data.get('version')!=3:raise ValueError('Unsupported source-map format')
        if 'sections' in data:
            if len(data['sections'])>10000:raise ValueError('Too many source-map sections')
            previous=(-1,-1)
            for section in data['sections']:
                offset=section['offset'];line=offset['line'];column=offset['column']
                if type(line)!=int or type(column)!=int or min(line,column)<0 or (line,column)<=previous:raise ValueError('Invalid source-map section order')
                previous=(line,column)
                if 'map' not in section:raise ValueError('External indexed source-map sections are unsupported')
                self._parse(section['map'],base_line+line,(base_column if line==0 else 0)+column,depth+1)
            return
        sources=data.get('sources',[]);content=data.get('sourcesContent',[]);paths=[self.source_path(source,data.get('sourceRoot','')) for source in sources]
        if len(sources)>100000:raise ValueError('Too many source-map sources')
        for index,path in enumerate(paths):
            if path is not None and index<len(content) and isinstance(content[index],str):self.contents[path]=content[index]
        mappings=data.get('mappings','')
        if not isinstance(mappings,str) or len(mappings)>16*1024*1024:raise ValueError('Source-map mappings exceed 16 MiB')
        source=original_line=original_column=0
        for row,line in enumerate(mappings.split(';')):
            column=0
            for segment in line.split(','):
                if not segment:continue
                self.count+=1
                if self.count>2000000:raise ValueError('Too many source-map segments')
                values=vlq(segment)
                if len(values) not in {1,4,5}:raise ValueError('Invalid source-map segment')
                column+=values[0]
                if column<0:raise ValueError('Negative generated column')
                if len(values)==1:
                    # An unmapped segment ends the preceding mapping on this row.
                    self.lines.setdefault(base_line+row,[]).append((column+(base_column if row==0 else 0),None,0,0));continue
                source+=values[1];original_line+=values[2];original_column+=values[3]
                if not 0<=source<len(paths) or min(original_line,original_column)<0:raise ValueError('Invalid original source-map position')
                generated_column=column+(base_column if row==0 else 0);path=paths[source]
                self.lines.setdefault(base_line+row,[]).append((generated_column,path,original_line,original_column))
                if path is not None:self.reverse.setdefault(path,[]).append((original_line,original_column,base_line+row,generated_column))

    def original(self,line,column):
        entries=self.lines.get(line,[])
        index=bisect_right([item[0] for item in entries],column)-1
        if index<0 or entries[index][1] is None:return None
        _,path,row,col=entries[index]
        return {'path':str(path),'line':row+1,'column':col+1}

    def generated(self,path,line):
        entries=self.reverse.get(Path(path).resolve(),[])
        candidates=[entry for entry in entries if entry[0]>=line-1]
        if not candidates:return None
        entry=min(candidates)
        return {'lineNumber':entry[2],'columnNumber':entry[3]}

    def verify_source(self,path):
        path=Path(path).resolve();content=self.contents.get(path)
        if content is not None and path.read_text(encoding='utf8').replace('\r\n','\n')!=content.replace('\r\n','\n'):
            raise ValueError('Source differs from the running bundle. Reload the development app before setting breakpoints.')
