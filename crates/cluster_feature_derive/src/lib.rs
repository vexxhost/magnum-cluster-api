extern crate proc_macro;
use heck::ToSnakeCase;
use proc_macro::TokenStream;
use quote::quote;
use syn::{parse_macro_input, DeriveInput, Token};

#[proc_macro_derive(ClusterFeatureValues, attributes(serde, variable))]
pub fn derive_cluster_variable_values(input: TokenStream) -> TokenStream {
    // Parse the input tokens into a syntax tree.
    let input = parse_macro_input!(input as DeriveInput);

    // Ensure we're working with a struct with named fields.
    let fields = if let syn::Data::Struct(data_struct) = &input.data {
        if let syn::Fields::Named(fields_named) = &data_struct.fields {
            &fields_named.named
        } else {
            panic!("ClusterFeatureValues can only be derived for structs with named fields");
        }
    } else {
        panic!("ClusterFeatureValues can only be derived for structs");
    };

    // Generate a variable for each field.
    let mut var_entries = Vec::new();

    for field in fields {
        let field_ident = field.ident.as_ref().unwrap();
        // Look for a serde(rename = "...") attribute on the field.
        let mut rename_value: Option<String> = None;
        // Look for a variable(required = false) or variable(default = "...") attribute.
        let mut required = true;
        let mut default_value: Option<String> = None;

        for attr in &field.attrs {
            if attr.path().is_ident("serde") {
                let _ = attr.parse_nested_meta(|meta| {
                    if meta.path.is_ident("rename") {
                        // Parse the "=" token
                        let _: Token![=] = meta.input.parse()?;

                        // Parse the string literal
                        let lit: syn::LitStr = meta.input.parse()?;
                        rename_value = Some(lit.value());
                    }
                    Ok(())
                });
            }
            if attr.path().is_ident("variable") {
                let _ = attr.parse_nested_meta(|meta| {
                    if meta.path.is_ident("required") {
                        let _: Token![=] = meta.input.parse()?;
                        let lit: syn::LitBool = meta.input.parse()?;
                        required = lit.value();
                    }
                    if meta.path.is_ident("default") {
                        let _: Token![=] = meta.input.parse()?;
                        let lit: syn::LitStr = meta.input.parse()?;
                        default_value = Some(lit.value());
                    }
                    Ok(())
                });
            }
        }

        // Use the rename value if present; otherwise, use the field name in snake_case.
        let var_name = match rename_value {
            Some(ref s) => s.clone(),
            None => field_ident.to_string().to_snake_case(),
        };

        let ty = &field.ty;
        if let Some(ref default) = default_value {
            var_entries.push(quote! {
                {
                    let mut schema = ClusterClassVariablesSchema::from_object::<#ty>();
                    schema.open_apiv3_schema.default = Some(serde_json::json!(#default));
                    ClusterClassVariables {
                        name: #var_name.into(),
                        metadata: None,
                        required: #required,
                        schema,
                    }
                }
            });
        } else {
            var_entries.push(quote! {
                ClusterClassVariables {
                    name: #var_name.into(),
                    metadata: None,
                    required: #required,
                    schema: ClusterClassVariablesSchema::from_object::<#ty>(),
                }
            });
        }
    }

    // Generate the final implementation.
    let expanded = quote! {
        impl ClusterFeatureVariables for Feature {
            fn variables(&self) -> Vec<ClusterClassVariables> {
                vec![
                    #(#var_entries),*
                ]
            }
        }
    };

    TokenStream::from(expanded)
}
