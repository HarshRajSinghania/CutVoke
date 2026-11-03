"""Real stdio MCP creative loop with original color/tone fixtures; no artistic claim."""
from __future__ import annotations
import argparse
import copy
import json
from pathlib import Path
import subprocess
import sys

from demo import MCP


def rat(n):
    return {"num": str(n), "den": "1"}


def span(a, b):
    return {"start": rat(a), "end": rat(b)}


def artifacts(project, asset):
    base = dict(schemaVersion=1, projectId=project.project_id, revision=project.revision,
                sequenceId=project.sequence.id)
    plan = dict(base, kind='plan', recipeId='product-demonstration',
        brief=dict(purpose='product-brand', audience='A first-time user', takeaway='A true result', successCriterion='Explain the task and condition'),
        delivery=dict(width=320, height=180, viewingContext='Landscape, sound on; also inspect small text'),
        assetRoles=[dict(id='source-a',assetId=asset, role='Synthetic demonstration, not a real product claim',sourceRange=span(0,4),provenance='illustration',rightsNote='Original test image')],
        protectedRanges=[dict(clipId='keep', range=span(4,8), reason='Required result and limitation')],
        beats=[dict(id='task',range=span(0,4),clipIds=['main'],selectionIds=['source-a'],intent='Introduce task',audioIntent='Synthetic tone, not speech',captionIntent='True condition'),
               dict(id='result',range=span(4,8),clipIds=['keep'],selectionIds=['source-a'],intent='Retain outcome',audioIntent='Keep tone',captionIntent='Required condition')],
        gaps=[], intentionalExceptions=[], reviewRequirements=['technical','continuous-av'])
    review = dict(base,kind='review',evidence=[dict(id='e1',kind='technical',range=span(0,4),artifact='notes/caption-comparison.json',inspection='inspected',inspector='deterministic fixture assertion',observation='Caption differs from the specified literal condition; no sensory judgment')],issues=[dict(id='i1',range=span(0,4),severity='major',observation='Wrong qualifier in fixture caption',evidenceIds=['e1'],suggestedAction='Correct caption only',preserve=['Keep timing, media and result'],status='open')],unassessed=['Full continuous AV and audience comprehension'])
    repair = dict(base,kind='repair',issueIds=['i1'],scope=span(0,4),commands=[dict(type='caption.update',payload=dict(captionId='condition',text='Demo condition'))],preserveClipIds=['main','keep'],rationale='Correct the fixture literal without retiming',recheckRanges=[span(0,8)],recheckRequirements=['technical','continuous-av'])
    return plan,review,repair



def run(output: Path):
    if not output.is_absolute() or output.exists():
        raise ValueError('output must be a new absolute directory; existing work is never replaced')
    output.mkdir(parents=True)
    for name in ('sources','notes','review','frames-before','frames-after'):
        (output/name).mkdir()
    for name,color,hz in [('task','red',440),('result','blue',880)]:
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i',f'color=c={color}:s=320x180:r=10:d=4',
            '-f','lavfi','-i',f'sine=frequency={hz}:sample_rate=48000:duration=4','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(output/'sources'/f'{name}.mp4')],check=True)
    client=None; lease=None
    def save(name,data):
        (output/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    try:
        client=MCP([sys.executable,'-m','cutvoke'],output/'projects.sqlite',output,None)
        def call(tool_name,**a):return client.call(tool_name,**a)
        found=call('creative_workflow',operation='list',query='demonstration',limit=3)
        assert any(r['id']=='product-demonstration' for r in found['recipes'])
        save('notes/recipe.json',call('creative_workflow',operation='recipe',recipeId='product-demonstration',locale='zh-CN'))
        for kind in ('plan','review','repair'):
            save('notes/'+kind+'-schema.json',call('creative_workflow',operation='schema',kind=kind))
        for name in ('clip.insert','caption.add','caption.update','edit.batch','export.enqueue'):
            call('editor_help',topic='command',command=name)
        created=call('create_project',projectId='creative-demo',name='Synthetic creative loop — no real product claim',width=320,height=180,fps=10)
        pid='creative-demo'; revision=created['revision']
        project_root=Path(call('project_directory',projectId=pid)['directory'])
        for name in ('sources','notes','review','frames-before','frames-after'):
            (output/name).rename(project_root/name)
        output=project_root
        imported=call('media_import',projectId=pid,paths=[str(output/'sources'/'task.mp4'),str(output/'sources'/'result.mp4')])['assets']
        edits=[]
        for i,key in enumerate(('main','keep')):
            edits.append(dict(type='clip.insert',payload=dict(trackId='v',**({'createTrackKind':'video'} if i==0 else {}),clipId=key,assetId=imported[i]['assetId'],timelineStart=rat(i*4),timelineEnd=rat((i+1)*4))))
        edits.append(dict(type='caption.add',payload=dict(captionId='condition',text='Wrong condition',start=rat(0),end=rat(4))))
        lease=call('edit_lock',projectId=pid,action='acquire',owner='creative-loop',ttlSeconds=120)['lease']['leaseId']
        payload={'commands':edits}
        call('command_preview',projectId=pid,expectedRevision=revision,type='edit.batch',payload=payload)
        revision=call('command_apply',projectId=pid,expectedRevision=revision,type='edit.batch',payload=payload,commandId='rough-cut',editLeaseId=lease)['revision']
        call('edit_lock',projectId=pid,action='release',leaseId=lease);lease=None
        def export(name):
            preflight=call('command_preview',projectId=pid,expectedRevision=revision,type='project.preflight',payload={})
            assert preflight['changedEntities'][0]['report']['readyToRender']
            queued=call('command_apply',projectId=pid,expectedRevision=revision,type='export.enqueue',commandId='export-'+name,payload={'outPath':str(project_root/'exports'/name),'quality':'high','overwrite':False})
            job=client.wait('export_job',pid,queued['changedEntities'][0]['jobId'])
            return Path(job['result']['output_path'])
        before_file=export('rough-cut.mp4')
        call('preview_frames',projectId=pid,expectedRevision=revision,times=[1,3.9,4.1,7],width=320,output_frames=output/'frames-before')
        snapshot=call('project_query',projectId=pid)['project']
        from types import SimpleNamespace
        plan,review,repair=artifacts(SimpleNamespace(project_id=pid,revision=revision,sequence=SimpleNamespace(id=snapshot['sequences'][0]['id'] if 'sequences' in snapshot else snapshot['sequence']['id'])),imported[0]['assetId'])
        plan['assetRoles'].append(dict(plan['assetRoles'][0],id='source-b',assetId=imported[1]['assetId'],role='Synthetic result, not a real product claim'))
        plan['beats'][1]['selectionIds']=['source-b']
        save('notes/caption-comparison.json',{'expected':'Demo condition','actual':'Wrong condition','source':'Fixed synthetic fixture requirement; no visual or semantic inference'})
        review['evidence'][0]['artifact']=str(output/'notes/caption-comparison.json')
        assert call('creative_workflow',operation='validate',document=plan)['contractValid']
        assert call('creative_workflow',operation='validate',document=review)['contractValid']
        for name,data in [('plan-before',plan),('review-before',review),('repair',repair)]:save('notes/'+name+'.json',data)
        before=call('project_query',projectId=pid)['project']
        preview=call('creative_workflow',operation='preview-repair',document=repair,plan=plan,review=review)
        save('notes/repair-preview.json',preview)
        assert preview['readyForCommandApply'] and call('project_query',projectId=pid)['project']==before
        lease=call('edit_lock',projectId=pid,action='acquire',owner='creative-loop',ttlSeconds=120)['lease']['leaseId']
        args=preview['nextCall']['arguments']
        fixed=call('command_apply',**args,editLeaseId=lease,commandId='repair-condition')
        repeated=call('command_apply',**args,editLeaseId=lease,commandId='repair-condition')
        assert fixed['revision']==repeated['revision'];revision=fixed['revision']
        call('edit_lock',projectId=pid,action='release',leaseId=lease);lease=None
        stale=call('creative_workflow',operation='preview-repair',document=repair,plan=plan,review=review)
        assert not stale['contractValid'] and 'nextCall' not in stale
        after=call('project_query',projectId=pid)['project']
        def seq(p):return next(s for s in p['sequences'] if s['id']==p['activeSequenceId']) if 'sequences' in p else p['sequence']
        assert seq(after)['tracks']==seq(before)['tracks'],'Media, timings and audio must remain byte-for-byte identical'
        assert seq(after)['captions'][0]['text']=='Demo condition'
        final_file=export('repaired.mp4')
        call('preview_frames',projectId=pid,expectedRevision=revision,times=[1,3.9,4.1,7],width=320,output_frames=output/'frames-after')
        # Automatic measurements inspect real final bytes; no claim of watching/listening.
        subprocess.run(['ffmpeg','-v','error','-i',str(final_file),'-f','null','-'],check=True)
        import numpy as np
        checks={}
        for when,channel,hz in [(1,0,440),(6,2,880)]:
            rgb=subprocess.check_output(['ffmpeg','-v','error','-ss',str(when),'-i',str(final_file),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'])
            image=np.frombuffer(rgb,np.uint8).reshape(180,320,3)
            pixel=image[10:30,10:30].mean(axis=(0,1))
            assert pixel[channel]>200 and pixel[(channel+1)%3]<35,pixel
            pcm=subprocess.check_output(['ffmpeg','-v','error','-ss',str(when),'-i',str(final_file),'-t','0.5','-vn','-f','f32le','-ac','1','-ar','48000','-'])
            samples=np.frombuffer(pcm,np.float32)
            peak=float(np.fft.rfftfreq(len(samples),1/48000)[np.abs(np.fft.rfft(samples)).argmax()])
            assert abs(peak-hz)<5,(peak,hz)
            checks[str(when)]={'pixelRGB':pixel.tolist(),'audioPeakHz':peak}
        probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(final_file)]))
        assert abs(float(probe['format']['duration'])-8)<0.2
        plan['revision']=revision;review['revision']=revision
        review['issues'][0]['status']='resolved'
        review['evidence'][0].update(artifact=str(output/'review/technical.json'),observation='Final caption equals fixture requirement; actual MP4 decoded and color/tone/duration checks passed')
        review['evidence'].append(dict(id='av-pending',kind='continuous-av',range=span(0,8),artifact=str(final_file),inspection='pending',inspector='Human or sensory-capable reviewer required',observation='Prepared and decoded; not watched or listened by this script'))
        save('review/technical.json',checks)
        save('notes/plan-after.json',plan);save('notes/review-after.json',review)
        validation=call('creative_workflow',operation='validate',document=review)
        assert validation['contractValid'] and validation['pendingEvidenceIds']==['av-pending']
        result={'projectId':pid,'revision':revision,'roughCut':str(before_file),'output':str(final_file),'checks':checks,
            'technicalValidationOnly':True,'creativeAcceptance':'not_assessed','pending':['Full AV sensory review','Audience comprehension and real-footage comparison'],
            'idempotentReplay':True,'oldEvidenceRejected':True,'mediaPreserved':True}
        save('result.json',result)
        return result
    finally:
        if client:
            if lease:
                client.call('edit_lock',projectId='creative-demo',action='release',leaseId=lease)
            client.close(output)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path,help='New absolute local directory, never replaced')
    args=parser.parse_args()
    print(json.dumps(run(args.output),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
