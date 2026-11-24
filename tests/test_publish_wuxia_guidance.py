from scripts.publish_wuxia_generation_guidance import baseline_row,publish

def test_baseline_is_deterministic_global_scoped_and_bounded():
 r=baseline_row();assert r==baseline_row()
 assert not r['category'] and not r['language'] and len(r['instruction'])<=4000
 assert '손잡이' in r['instruction'] and '무협 웹툰' in r['instruction']

def test_approved_baseline_is_read_back_without_duplicate_write():
 row={**baseline_row(),'version':99,'status':'approved'}
 class Store:
  def request(self,method,table,**kwargs):
   assert method=='GET';return [row],None
 assert publish(Store())=={'id':row['id'],'version':99,'status':'approved'}
