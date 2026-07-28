module "network" {
  source = "./modules/network"
}

resource "aws_security_group" "api" {
  vpc_id = module.network.vpc_id
}

resource "aws_instance" "api" {
  vpc_security_group_ids = [aws_security_group.api.id]
}

resource "aws_eip" "api" {
  instance = aws_instance.api.id
}

resource "aws_route53_record" "api" {
  records = [aws_eip.api.public_ip]
}
