data "oci_core_images" "oracle_linux_arm" {
  compartment_id           = var.compartment_ocid
  operating_system         = "Oracle Linux"
  operating_system_version = "9"
  shape                    = "VM.Standard.A1.Flex"
  sort_by                  = "TIMECREATED"
  sort_order               = "DESC"
}

data "oci_objectstorage_namespace" "deployment" {
  compartment_id = var.compartment_ocid
}

resource "oci_core_vcn" "mm_rag" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = ["10.88.0.0/16"]
  display_name   = "mm-rag-learning-vcn"
  dns_label      = "mmrag"
  freeform_tags  = var.freeform_tags
}

resource "oci_core_internet_gateway" "public" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.mm_rag.id
  display_name   = "mm-rag-learning-internet-gateway"
  enabled        = true
  freeform_tags  = var.freeform_tags
}

resource "oci_core_route_table" "public" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.mm_rag.id
  display_name   = "mm-rag-learning-public-routes"
  freeform_tags  = var.freeform_tags

  route_rules {
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_internet_gateway.public.id
  }
}

resource "oci_core_network_security_group" "edge" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.mm_rag.id
  display_name   = "mm-rag-learning-edge"
  freeform_tags  = var.freeform_tags
}

resource "oci_core_network_security_group_security_rule" "ingress" {
  for_each = {
    http  = { port = 80, source = "0.0.0.0/0" }
    https = { port = 443, source = "0.0.0.0/0" }
    ssh   = { port = 22, source = var.operator_cidr }
  }

  network_security_group_id = oci_core_network_security_group.edge.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = each.value.source
  source_type               = "CIDR_BLOCK"

  tcp_options {
    destination_port_range {
      min = each.value.port
      max = each.value.port
    }
  }
}

resource "oci_core_network_security_group_security_rule" "egress" {
  network_security_group_id = oci_core_network_security_group.edge.id
  direction                 = "EGRESS"
  protocol                  = "all"
  destination               = "0.0.0.0/0"
  destination_type          = "CIDR_BLOCK"
}

resource "oci_core_subnet" "public" {
  compartment_id             = var.compartment_ocid
  vcn_id                     = oci_core_vcn.mm_rag.id
  cidr_block                 = "10.88.1.0/24"
  display_name               = "mm-rag-learning-public-subnet"
  dns_label                  = "app"
  prohibit_public_ip_on_vnic = false
  route_table_id             = oci_core_route_table.public.id
  freeform_tags              = var.freeform_tags
}

resource "oci_core_instance" "app" {
  availability_domain = var.availability_domain
  compartment_id      = var.compartment_ocid
  display_name        = "mm-rag-learning"
  shape               = "VM.Standard.A1.Flex"
  freeform_tags       = var.freeform_tags

  shape_config {
    ocpus         = var.instance_ocpus
    memory_in_gbs = var.instance_memory_gbs
  }

  create_vnic_details {
    assign_public_ip = true
    display_name     = "mm-rag-learning"
    hostname_label   = "app"
    nsg_ids          = [oci_core_network_security_group.edge.id]
    subnet_id        = oci_core_subnet.public.id
  }

  metadata = {
    ssh_authorized_keys = var.ssh_public_key
    user_data = base64encode(templatefile("${path.module}/cloud-init.yaml.tftpl", {
      repository_url = "https://github.com/mvyas412/ai-projects.git"
    }))
  }

  instance_options {
    are_legacy_imds_endpoints_disabled = true
  }

  source_details {
    source_id               = data.oci_core_images.oracle_linux_arm.images[0].id
    source_type             = "image"
    boot_volume_size_in_gbs = var.boot_volume_gbs
  }

  lifecycle {
    # OCI user_data is create-only; replacements require an explicit rebuild decision.
    ignore_changes = [metadata["user_data"]]
  }
}

resource "oci_objectstorage_bucket" "backups" {
  compartment_id = var.compartment_ocid
  namespace      = data.oci_objectstorage_namespace.deployment.namespace
  name           = var.backup_bucket_name
  access_type    = "NoPublicAccess"
  storage_tier   = "Standard"
  versioning     = "Enabled"
  freeform_tags  = var.freeform_tags
}

# The application host is the only principal allowed to create backup objects.
# Bucket administration, object listing, reads, overwrites, and deletion stay denied.
resource "oci_identity_dynamic_group" "backup_uploader" {
  compartment_id = var.tenancy_ocid
  name           = "mm-rag-learning-backup-uploader"
  description    = "MM-RAG learning host instance principal for encrypted backup upload"
  matching_rule  = "ALL {instance.id = '${oci_core_instance.app.id}'}"
  freeform_tags  = var.freeform_tags
}

resource "oci_identity_policy" "backup_uploader" {
  compartment_id = var.compartment_ocid
  name           = "mm-rag-learning-backup-uploader"
  description    = "Allow the MM-RAG host to create encrypted objects only in its backup bucket"
  statements = [
    "Allow dynamic-group ${oci_identity_dynamic_group.backup_uploader.name} to manage objects in compartment id ${var.compartment_ocid} where all {target.bucket.name = '${oci_objectstorage_bucket.backups.name}', request.permission = 'OBJECT_CREATE'}",
  ]
  freeform_tags = var.freeform_tags
}

resource "oci_budget_budget" "learning_guardrail" {
  compartment_id = var.tenancy_ocid
  amount         = var.monthly_budget_usd
  reset_period   = "MONTHLY"
  target_type    = "COMPARTMENT"
  targets        = [var.compartment_ocid]
  display_name   = "mm-rag-learning-monthly-budget"
}

resource "oci_budget_alert_rule" "forecast" {
  budget_id      = oci_budget_budget.learning_guardrail.id
  display_name   = "mm-rag-learning-forecast"
  type           = "FORECAST"
  threshold      = 1
  threshold_type = "ABSOLUTE"
  recipients     = var.budget_alert_email
}

resource "oci_budget_alert_rule" "actual" {
  budget_id      = oci_budget_budget.learning_guardrail.id
  display_name   = "mm-rag-learning-actual"
  type           = "ACTUAL"
  threshold      = 1
  threshold_type = "ABSOLUTE"
  recipients     = var.budget_alert_email
}
