# smart-novel-search-novel-lambda
小説検索用関数. APIゲートウェイにつなげる

## 設定
| 項目 | 値 |
| ---- | ---- |
| ランタイム | Python 3.8 |
| メモリ | 512 MB |
| タイムアウト | 10 s |
| layer | smartnovel-search-layer |
| VPC |  smartnovel-vpc-dev |

## 環境変数
| 変数名 | 値 |
| ---- | ---- |
| ES_HOST | vpc-smartnovel-es-dev-j74tj7mufmh6cmogkjcudm6uq4.ap-northeast-1.es.amazonaws.com |
| ES_INDEX | smart-novel |
| ES_REGION | ap-northeast-1 |