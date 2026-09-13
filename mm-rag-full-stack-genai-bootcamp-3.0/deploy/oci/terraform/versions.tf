terraform {
  required_version = ">= 1.16.0, < 1.17.0"

  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "~> 8.25"
    }
  }
}

provider "oci" {
  region = var.region
}
