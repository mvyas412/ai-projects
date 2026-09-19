variable "region" {
  description = "OCI home region selected by the operator."
  type        = string
}

variable "compartment_ocid" {
  description = "Compartment that owns the learning deployment."
  type        = string
  sensitive   = true
}

variable "tenancy_ocid" {
  description = "Root tenancy OCID where OCI stores the budget resource."
  type        = string
  sensitive   = true
}

variable "availability_domain" {
  description = "Availability domain that has A1 capacity."
  type        = string
}

variable "ssh_public_key" {
  description = "Public key used for the opc account. Never supply a private key."
  type        = string
}

variable "operator_cidr" {
  description = "Exact operator source CIDR permitted to use SSH, for example 203.0.113.8/32."
  type        = string

  validation {
    condition     = can(cidrhost(var.operator_cidr, 0)) && tonumber(split("/", var.operator_cidr)[1]) >= 24
    error_message = "operator_cidr must be a valid, narrowly scoped /24 or smaller network. Prefer /32."
  }
}

variable "instance_ocpus" {
  description = "ARM OCPUs. The default leaves room inside OCI's published Always Free aggregate allowance."
  type        = number
  default     = 2

  validation {
    condition     = var.instance_ocpus >= 1 && var.instance_ocpus <= 4
    error_message = "instance_ocpus must be between 1 and 4."
  }
}

variable "instance_memory_gbs" {
  description = "ARM memory in GB. The default is intentionally conservative for a learning host."
  type        = number
  default     = 12

  validation {
    condition     = var.instance_memory_gbs >= 6 && var.instance_memory_gbs <= 24
    error_message = "instance_memory_gbs must be between 6 and 24."
  }
}

variable "boot_volume_gbs" {
  description = "Boot volume size in GB."
  type        = number
  default     = 100
}

variable "backup_bucket_name" {
  description = "Globally unique private Object Storage bucket name for encrypted backup bundles."
  type        = string
}

variable "monthly_budget_usd" {
  description = "Monthly budget guardrail. OCI budgets require a whole-number amount."
  type        = number
  default     = 1

  validation {
    condition     = var.monthly_budget_usd >= 1 && floor(var.monthly_budget_usd) == var.monthly_budget_usd
    error_message = "monthly_budget_usd must be a positive whole number."
  }
}

variable "budget_alert_email" {
  description = "Email address that receives forecast and actual-spend alerts."
  type        = string
  sensitive   = true
}

variable "freeform_tags" {
  description = "Optional ownership and learning-purpose tags."
  type        = map(string)
  default = {
    application = "mm-rag"
    environment = "learning"
    managed-by  = "terraform"
  }
}
