FROM circleci/ruby:2.5.1

RUN sudo apt-get install -y python-pip
COPY . /home/circleci/repo
RUN sudo chown circleci. -R /home/circleci/repo