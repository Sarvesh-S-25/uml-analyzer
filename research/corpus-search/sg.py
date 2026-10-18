import json,sys,urllib.request,urllib.parse
qs=["file:\.mdj$ UMLClass count:all archived:yes",
    "file:\.mdj$ UMLOperation count:all",
    "file:\.mdj$ UMLAttribute count:all archived:yes",
    "file:\.mdj$ UMLInterface count:all",
    "file:\.mdj$ UMLGeneralization count:all",
    "file:\.mdj$ UMLClass count:all lang:json",
    "file:\.mdj$ UMLClass count:all fork:no archived:no",
    "file:\.mdj$ UMLClassDiagram count:all",
    "file:\.mdj$ UMLAssociation count:all",
    "file:\.mdj$ \"MyProject\" UMLClass count:all"]
repos=json.load(open('sg_repos.json'))
files={}
for q in qs:
    url="https://sourcegraph.com/.api/search/stream?"+urllib.parse.urlencode({"q":q,"display":"5000"})
    req=urllib.request.Request(url,headers={"Accept":"text/event-stream"})
    try: body=urllib.request.urlopen(req,timeout=90).read().decode('utf8','replace')
    except Exception as e: print(q,e); continue
    n=0
    for line in body.splitlines():
        if line.startswith('data: ['):
            try: arr=json.loads(line[6:])
            except: continue
            for m in arr:
                if isinstance(m,dict) and m.get('repository'):
                    repos[m['repository']]=m.get('repoStars',0); n+=1
                    if m.get('path'): files.setdefault(m['repository'],set()).add(m['path'])
    print(len(repos),n,q)
json.dump(repos,open('sg_repos.json','w'))
json.dump({k:sorted(v) for k,v in files.items()},open('sg_files.json','w'))
