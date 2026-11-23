import os
from pathlib import Path
import subprocess


def test_default_release_tag_supports_linked_worktree(tmp_path):
    repo=tmp_path/'repo';worktree=tmp_path/'linked'
    subprocess.run(['git','init','-q',str(repo)],check=True)
    subprocess.run(['git','-C',str(repo),'-c','user.name=Synthetic','-c','user.email=synthetic@example.test','commit','--allow-empty','-qm','synthetic'],check=True)
    subprocess.run(['git','-C',str(repo),'worktree','add','-q','--detach',str(worktree)],check=True)
    source=(Path(__file__).parents[1]/'assets/templates/publish-image-harbor.sh.example').read_text()
    start=source.index('if [[ -z "${IMAGE_TAG:-}" ]]; then')
    end=source.index('if [[ "$IMAGE_TAG" =~',start)
    script=source[start:end]+'\nprintf "%s" "$IMAGE_TAG"\n'
    env=os.environ.copy();env.pop('IMAGE_TAG',None)
    for root in (repo,worktree):
        env['ROOT']=str(root)
        r=subprocess.run(['bash','-c',script],env=env,capture_output=True,text=True,check=True)
        sha=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
        assert r.stdout=='slai-sc-'+sha+'-1-1'
    assert (worktree/'.git').is_file()
