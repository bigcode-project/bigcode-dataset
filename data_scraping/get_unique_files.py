import text2code_dataset.dataset.filter_dask as filter
from text2code_dataset.dataset.licenses import safe_licenses_the_stack_11
from text2code_dataset.dataset.opt_out import opt_out_github_login_the_stack_12
import toolkit_run.dask.apply as apply



def filter_per_bucket_java_all(data):
    # names of pandas dataframes are the same as subfolders in the src folder, so one
    # dataframe per subfolder with many buckets. 
    # there must be the same number of buckets and with the same indexes in each dataframe
    ri = data['ri']
    fi = data['fi']
    lic = data['lic']

    lic.loc[lic['file'].isna(), 'file'] = 'None'
    idx = lic.groupby(["ri_id", 'file'])['confidence'].transform(max) == lic['confidence']
    lic1 = lic[idx]
    lic1 = lic1.groupby('ri_id').apply(lambda x: list(set(x['license']))).to_frame('licenses')

    ri1 = ri.merge(lic1, left_on='id', right_on='ri_id', how='right')

    fi = fi[fi['lang_ex'] == 'Java']
    fi1 = fi.merge(ri1, left_on='ri_id', right_on='id', how='inner')

    assert fi1['ri_id'].nunique() == fi['ri_id'].nunique()
    
    fi1 = fi1.sort_values('forks_count')
    fi_forks = fi1.groupby('hexsha').last()
    fi_forks = fi_forks[['path', 'name', 'head_hexsha', 'licenses', 'forks_count',
           'forks_event_min_datetime', 'forks_event_max_datetime']]
    fi_forks = fi_forks.rename(columns={
        'forks_count':'max_forks_count',
        'path': 'max_forks_repo_path',
        'name': 'max_forks_repo_name',
        'head_hexsha': 'max_forks_repo_head_hexsha',
        'licenses': 'max_forks_repo_licenses',
        'forks_event_min_datetime': 'max_forks_repo_forks_event_min_datetime',
        'forks_event_max_datetime': 'max_forks_repo_forks_event_max_datetime'
    })
    fi1 = fi1.sort_values('issues_count')
    fi_issues = fi1.groupby('hexsha').last()

    fi_issues = fi_issues[['path', 'name', 'head_hexsha', 'licenses', 'issues_count',
           'issues_event_min_datetime', 'issues_event_max_datetime']]
    fi_issues = fi_issues.rename(columns={
        'issues_count':'max_issues_count',
        'path': 'max_issues_repo_path',
        'name': 'max_issues_repo_name',
        'head_hexsha': 'max_issues_repo_head_hexsha',
        'licenses': 'max_issues_repo_licenses',
        'issues_event_min_datetime': 'max_issues_repo_issues_event_min_datetime',
        'issues_event_max_datetime': 'max_issues_repo_issues_event_max_datetime'
    })
    fi1 = fi1.sort_values('stars_count')
    fi_stars = fi1.groupby('hexsha').last()

    fi_stars = fi_stars[['size', 'ext', 'lang_ex', 'path', 'name', 'head_hexsha', 'licenses', 'stars_count',
           'stars_event_min_datetime', 'stars_event_max_datetime']]
    fi_stars = fi_stars.rename(columns={
        'lang_ex': 'lang',
        'stars_count':'max_stars_count',
        'path': 'max_stars_repo_path',
        'name': 'max_stars_repo_name',
        'head_hexsha': 'max_stars_repo_head_hexsha',
        'licenses': 'max_stars_repo_licenses',
        'stars_event_min_datetime': 'max_stars_repo_stars_event_min_datetime',
        'stars_event_max_datetime': 'max_stars_repo_stars_event_max_datetime'
    })
    fi2 = fi_stars.join(fi_issues).join(fi_forks)
    fi2 = fi2.reset_index()
    return fi2


def filter_per_bucket(data):
    # names of pandas dataframes are the same as subfolders in the src folder, so one
    # dataframe per subfolder with many buckets. 
    # there must be the same number of buckets and with the same indexes in each dataframe
    ri = data['ri']
    fi = data['fi']
    lic = data['lic']

    idx = lic.groupby(["ri_id", 'file'])['confidence'].transform(max) == lic['confidence']
    lic1 = lic[idx]
    lic1 = lic1.groupby('ri_id').filter(lambda x: x['license'].isin(safe_licenses_the_stack_11).all())
    lic1 = lic1.groupby('ri_id').apply(lambda x: list(set(x['license']))).to_frame('licenses')


    opt_out_github_login_the_stack_12_lc = [el.lower() for el in opt_out_github_login_the_stack_12]

    ri['user_login'] = ri['name'].str.split('/', expand=True)[0].str.lower()
    ri = ri[ri['user_login'].isin(opt_out_github_login_the_stack_12_lc) == False]
    ri1 = ri.merge(lic1, left_on='id', right_on='ri_id', how='right')

    fi = fi[fi['lang_ex'] != 'other']
    fi1 = fi.merge(ri1, left_on='ri_id', right_on='id', how='inner')
    
    fi1 = fi1.sort_values('forks_count')
    fi_forks = fi1.groupby('hexsha').last()
    fi_forks = fi_forks[['path', 'name', 'head_hexsha', 'licenses', 'forks_count',
           'forks_event_min_datetime', 'forks_event_max_datetime']]
    fi_forks = fi_forks.rename(columns={
        'forks_count':'max_forks_count',
        'path': 'max_forks_repo_path',
        'name': 'max_forks_repo_name',
        'head_hexsha': 'max_forks_repo_head_hexsha',
        'licenses': 'max_forks_repo_licenses',
        'forks_event_min_datetime': 'max_forks_repo_forks_event_min_datetime',
        'forks_event_max_datetime': 'max_forks_repo_forks_event_max_datetime'
    })
    fi1 = fi1.sort_values('issues_count')
    fi_issues = fi1.groupby('hexsha').last()

    fi_issues = fi_issues[['path', 'name', 'head_hexsha', 'licenses', 'issues_count',
           'issues_event_min_datetime', 'issues_event_max_datetime']]
    fi_issues = fi_issues.rename(columns={
        'issues_count':'max_issues_count',
        'path': 'max_issues_repo_path',
        'name': 'max_issues_repo_name',
        'head_hexsha': 'max_issues_repo_head_hexsha',
        'licenses': 'max_issues_repo_licenses',
        'issues_event_min_datetime': 'max_issues_repo_issues_event_min_datetime',
        'issues_event_max_datetime': 'max_issues_repo_issues_event_max_datetime'
    })
    fi1 = fi1.sort_values('stars_count')
    fi_stars = fi1.groupby('hexsha').last()

    fi_stars = fi_stars[['size', 'ext', 'lang_ex', 'path', 'name', 'head_hexsha', 'licenses', 'stars_count',
           'stars_event_min_datetime', 'stars_event_max_datetime']]
    fi_stars = fi_stars.rename(columns={
        'lang_ex': 'lang',
        'stars_count':'max_stars_count',
        'path': 'max_stars_repo_path',
        'name': 'max_stars_repo_name',
        'head_hexsha': 'max_stars_repo_head_hexsha',
        'licenses': 'max_stars_repo_licenses',
        'stars_event_min_datetime': 'max_stars_repo_stars_event_min_datetime',
        'stars_event_max_datetime': 'max_stars_repo_stars_event_max_datetime'
    })
    fi2 = fi_stars.join(fi_issues).join(fi_forks)
    fi2 = fi2.reset_index()
    return fi2

def group_globally(data):
    fi1  = data['groupedby']
    
    fi1 = fi1.sort_values('max_forks_count')
    fi_forks = fi1.groupby('hexsha').last()
    fi_forks = fi_forks[[
        'max_forks_repo_path', 'max_forks_repo_name', 'max_forks_repo_head_hexsha', 'max_forks_repo_licenses',
        'max_forks_count', 'max_forks_repo_forks_event_min_datetime', 'max_forks_repo_forks_event_max_datetime']]
    
    fi1 = fi1.sort_values('max_issues_count')
    fi_issues = fi1.groupby('hexsha').last()
    fi_issues = fi_issues[[
        'max_issues_repo_path', 'max_issues_repo_name', 'max_issues_repo_head_hexsha', 'max_issues_repo_licenses',
        'max_issues_count','max_issues_repo_issues_event_min_datetime', 'max_issues_repo_issues_event_max_datetime']]

    fi1 = fi1.sort_values('max_stars_count')
    fi_stars = fi1.groupby('hexsha').last()
    fi_stars = fi_stars[[
        'size', 'ext', 'lang',
        'max_stars_repo_path', 'max_stars_repo_name', 'max_stars_repo_head_hexsha', 'max_stars_repo_licenses',
        'max_stars_count',  'max_stars_repo_stars_event_min_datetime', 'max_stars_repo_stars_event_max_datetime']]

    fi2 = fi_stars.join(fi_issues).join(fi_forks)
    fi2 = fi2.reset_index()
    return fi2

class DRParams(apply.DaskRunParams):
    @property
    def max_cluster_size(self):
        return 60

    def run(self, client):
        # Instantiate the Dask Dataframe processor
        dapply = filter.DaskDataframesFilterGroupApplyBucketed(
            filter_func=filter_per_bucket,
            groupby_apply_func=group_globally,
            src_paths=[
                '/dataset/repositories_zipped2_logs/indexes/repo_info/df_2022-01-24_all_licenses_no_vanity/',
                '/dataset/repositories_zipped2_logs/indexes/repo_info/df_github_v2_all_licenses_clean/'
            ],
            dst_root='/dataset/the_stack_v12_permissive_lic_files',
            groupby_column='hexsha',
            groupby_src_universe=120,#self.max_cluster_size,
            groupby_dst_universe_ff_power=2,
            filtered_key = 'filtered',
            groupedby_key = 'groupedby'
        )

        res = dapply.run(client, recompute=False)

        
        
        
