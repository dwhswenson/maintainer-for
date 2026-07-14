FROM public.ecr.aws/lambda/python:3.13

COPY lambda/requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY lambda/src/ ${LAMBDA_TASK_ROOT}/

CMD ["handler.lambda_handler"]
