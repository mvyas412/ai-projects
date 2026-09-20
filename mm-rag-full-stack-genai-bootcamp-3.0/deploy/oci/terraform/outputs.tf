output "instance_id" {
  value = oci_core_instance.app.id
}

output "public_ip" {
  value = oci_core_instance.app.public_ip
}

output "backup_bucket_name" {
  value = oci_objectstorage_bucket.backups.name
}

output "object_storage_namespace" {
  value = data.oci_objectstorage_namespace.deployment.namespace
}

output "deployment_summary" {
  value = {
    environment = "learning"
    shape       = oci_core_instance.app.shape
    ocpus       = var.instance_ocpus
    memory_gbs  = var.instance_memory_gbs
    public_tcp  = [80, 443]
    backup_auth = "instance-principal-create-only"
  }
}
