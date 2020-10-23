import json
from typing import Dict
import logging
import traceback
from pydantic import ValidationError
from elasticsearch import ElasticsearchException

from utils.date_utils import timestamp_to_iso, jst_now_str
from models import NovelFacetedSearch, SearchRequests, SearchResponse
from connections import build_client
from exceptions import InvalidESDocumentError

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def err(status_code: int, err_reason):
    traceback.print_exc()
    response_data = {
        "message": err_reason
    }
    return json.dumps(response_data),


def execute_search(es, faceted_search_model, params: Dict):
    query = params["search_text"]
    filters = params["filters"]
    offset = params["offset"]
    limit = params["limit"]
    sort = {}
    if "order" in params and params["order"] == "latest":
        sort = {
            "updated_time": {"order": "desc"},
            "_score": {"order": "desc"},
        }
    else:
        pass
    date_from = params["date"]["from"]
    date_to = params["date"]["to"]
    date_range_filter = {
        'updated_time': {
            "time_zone": "+09:00",
            'gte': date_from, "format": "yyyy-MM-dd HH:mm:ss",
            'lte': date_to, "format": "yyyy-MM-dd HH:mm:ss"
        },
    }
    '''build faceted search'''
    logger.info(f'filters={filters}')
    ts = faceted_search_model(query, filters=filters)
    '''
    Additional Condition
    ._s is search object internal FasetedSearch class
    '''
    ts._s = (ts._s.using(es)
             .filter("range", **date_range_filter)
             .sort(sort)
             [offset:offset + limit]
             )
    response = ts.execute()
    return response


def extract_novels(response):
    try:
        novels = []
        for hit in response:
            hit_dict = hit.to_dict()
            novel = {
                "title": hit_dict["title"],
                "author": hit_dict["author"],
                "url": hit_dict["url"],
                "site_name": hit_dict["site_name"],
                "genre": hit_dict["genre"],
                "updated_time": timestamp_to_iso(hit_dict["updated_time"] / 1000),
                "tag": [{"name": t} for t in hit_dict["tag"]]
            }
            # if "highlight" in hit.meta.to_dict() and "description" in hit.meta.highlight.to_dict():
            #     novel["highlight"] = hit.meta.highlight.to_dict()["description"][0]
            # else:
            #     novel["highlight"] = None
            novels.append(novel)
    except Exception as e:
        logger.error(f"DOCUMENT DATA ERROR,{e}")
        raise InvalidESDocumentError

    return novels


def extract_facets(response) -> Dict:
    """Return Facet name and count object
        {
            "tag":{
                "スニーカー":20,
                "流行":20
            }
        }
    """
    facets = {}
    for facet_name in response.facets:
        facets[facet_name] = dict(
            map(lambda x: (x[0], x[1]), response.facets[facet_name]))
    return facets


def create_response_data(response) -> Dict:
    total = response.hits.total.value
    novels = extract_novels(response)
    facets = extract_facets(response)
    ret = {
        "count": len(response.hits), 
        "total": total,
        "novels": novels,
        "facets": facets
    }
    return ret


def lambda_handler(event, context):
    """Search Web-novel Documents on Elasticsearch
    1. Validation Check Requests
    2. Search Document
    3. Transfrom Search Response to HTTP response data
    Args:
        request (flask.Request): HTTP request object: POST Content-Type:application/json
            "search_text": "" Required, must be string, max_lenght: 200
            "filters":{ Optional
                "tag":[], Optional, type:array of string
            },
            "date":{ Optional
                "from":"2000-01-01", Optional, string must be date format yyyy-mm-dd, default today - 30 days
                "to":"2020-05-24", Optional, string must be date format yyyy-mm-dd, default today
            },
            "offset":0, Optional default 0
            "limit":1000, Optional default 10 min: 1, max:1000
            "order":"latest" Optional type:string, latest/score, default latest
    Returns: Content-Type:application/json
        total [number]: total_count of search results, not equal returned tweet number
        id [str]:
        ogtitle [str]: title of novel
        ogsite_name [str]: site name where aricle is posted
        ogurl [str]: URL of novel
        ogdescription [str]: novel description
        ogimage [str]: URL of novel's image
        tag [List[str]]: keyword of novel
        created_at: novel created date time
        facets [Dict]: {
            tag [Dict]: { Word1: Count, Word2: Count}
            ここで帰ってくるキーワードをRequestのfiltersに入れることが可能
            Countの数字には自分自身のフィルタは考慮されていない。
            例：age:10, gender:男性　でフィルタした場合、
                genderにはage:10でフィルタされたカウントが返却される。つまり10代男性、10代女性のカウントが返却
                ageにはgender:男性でフィルタされたカウントが返却される。つまり各年代の男性のカウントが返却
        }
    }
    ERROR:
        400:
            - Validation error
        500:
            - Database connection error: Elasticsearch Exception
            - Internal Data error: Document don't have required field
            - Unexpected error
    """
    try:
        request_json = event
        if "search_text" not in request_json:
            request_json["search_text"] = ""
        logger.info(f"Request parameters:{request_json}")
        # Request Validation Check and Delete Unnecessary data
        parameters = SearchRequests(**request_json).dict()
        date_from = parameters["date"]["from_"].strftime("%Y-%m-%d %H:%M:%S")
        date_to = parameters["date"]["to"].strftime("%Y-%m-%d %H:%M:%S")
        parameters["date"].pop("from_")
        parameters["date"]["from"] = date_from
        parameters["date"]["to"] = date_to

        es = build_client()

        logger.info(f"BEGIN search, parameters:{parameters}")
        response = execute_search(es, NovelFacetedSearch, parameters)
        logger.info("END search")

        logger.info("Search results, total_count:{total}".format(
            total=response.hits.total.value))
        response_data = create_response_data(response)
        response_data = SearchResponse(**response_data).dict()
        return response_data
    except ValidationError as e:
        logger.error(f"ValidationError:{e}")
        return err(400, f"Validation error:{e}")
    except ElasticsearchException as e:
        logger.error(f"ElasticsearchException:{e}")
        return err(500, "Database connection error")
    except InvalidESDocumentError as e:
        logger.error(f"InvalidESDocumentError:{e}")
        return err(500, "Internal Data error")
    except Exception:
        return err(500, "Unexpected error")
