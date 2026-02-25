from google.oauth2 import service_account
import datetime
from google.cloud import secretmanager
# class GetSecretRequest(proto.Message):
from google.cloud.secretmanager_v1.types.service import GetSecretRequest
class secret_getter_cls:
    def __init__(self):
        '''
        '''
        print(f'secret_getter_cls started')
        self.project_id = "finbot-408300"
        self.client = secretmanager.SecretManagerServiceClient()

    def get_action(self, secret_name=None):
        '''
        '''
        self.secretnamev01 = f'projects/{self.project_id}/secrets/{secret_name}/versions/latest'
        try:
            response = self.client.access_secret_version(name =  self.secretnamev01)
        except Exception as e:
            raise RuntimeError(
                f"Failed to access secret '{secret_name}' "
                f"from project '{self.project_id}': {e}"
            ) from e
        return response.payload.data.decode('utf-8')
 
def main():
    sgc = secret_getter_cls()
    sv = sgc.get_action('openaikey')
    print(sv)

if __name__ == '__main__':
    main()
