from fastapi import APIRouter, Depends

from src.controllers.access import analyst, intake_reader
from src.schemas.inputs import NewBatch
from src.services import intake

router = APIRouter(prefix='/batches')


@router.get('')
def index(user=Depends(intake_reader)):
    return intake.list_batches()


@router.post('', status_code=202)
def create(payload: NewBatch, user=Depends(analyst)):
    return intake.submit_batch(payload, user['username'])


@router.get('/{batch_id}')
def detail(batch_id: int, user=Depends(intake_reader)):
    return intake.get_batch(batch_id)


@router.post('/{batch_id}/retry', status_code=202)
def retry(batch_id: int, user=Depends(analyst)):
    return intake.retry_batch(batch_id, user['username'])
